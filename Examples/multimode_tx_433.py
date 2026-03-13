# =============================================================================
# Multi-Mode Transmitter — NUCLEO-WL55 @ 433.5 MHz
# Modes: LoRa | GFSK | GMSK | BPSK | OOK | 2-FSK | 4-FSK
# Each mode runs for 10 seconds, then loops
#
# Hardware: STM32WL55 internal Sub-GHz radio (SX126x command set)
# TX power: -17 dBm (minimum) on RFO_LP path
#
# Native modulations per STM32WL55 datasheet:
#   LoRa, (G)FSK, (G)MSK, BPSK, 2-FSK  <- all supported in silicon
#   OOK  <- NOT natively supported; simulated via CW-carrier toggle
#   4-FSK <- NOT natively supported; simulated via per-symbol freq switching
#
# Upload:
#   mpremote cp multimode_tx_433.py :main.py && mpremote reset
# =============================================================================

import time
import pyb
from machine import SPI, Pin
import stm

# Opcodes
_STANDBY        = 0x80
_SET_TCXO       = 0x97
_CALIBRATE      = 0x89
_CAL_IMAGE      = 0x98
_SET_REGULATOR  = 0x96
_SET_PKT_TYPE   = 0x8A
_SET_RF_FREQ    = 0x86
_SET_PA_CONFIG  = 0x95
_SET_TX_PARAMS  = 0x8E
_SET_MOD_PARAMS = 0x8B
_SET_PKT_PARAMS = 0x8C
_SET_BUF_ADDR   = 0x8F
_WRITE_BUF      = 0x0E
_SET_DIO_IRQ    = 0x08
_CLR_IRQ        = 0x02
_SET_TX         = 0x83
_SET_TX_CW      = 0xD1   # SetTxContinuousWave - unmodulated carrier ON

# Packet type codes
PKT_GFSK = 0x00
PKT_LORA = 0x01
PKT_BPSK = 0x03

# GFSK pulse shapes
SHAPE_NONE = 0x00   # Plain FSK
SHAPE_BT03 = 0x08   # Gaussian BT=0.3 -> GMSK
SHAPE_BT05 = 0x09   # Gaussian BT=0.5 -> GFSK

# Antenna switch pins (NUCLEO-WL55, UM2592 Table 12)
# TX LP <=15 dBm : CTRL1=1 CTRL2=1 CTRL3=0
# Idle/sleep     : CTRL1=0 CTRL2=0 CTRL3=0
_ctrl1 = Pin("FE_CTRL1", Pin.OUT, value=0)
_ctrl2 = Pin("FE_CTRL2", Pin.OUT, value=0)
_ctrl3 = Pin("FE_CTRL3", Pin.OUT, value=0)

_spi = SPI("SUBGHZ")

# =============================================================================
# Low-level helpers
# =============================================================================

def _cmd(buf):
    stm.subghz_cs(False)
    _spi.write(buf)
    stm.subghz_cs(True)

def _ant_tx_lp():
    _ctrl1.value(1); _ctrl2.value(1); _ctrl3.value(0)

def _ant_off():
    _ctrl1.value(0); _ctrl2.value(0); _ctrl3.value(0)

def _freq_word(hz):
    w = int(hz / 32_000_000 * (1 << 25))
    return bytes([(w>>24)&0xFF,(w>>16)&0xFF,(w>>8)&0xFF,w&0xFF])

def _bitrate_word(bps):
    # BitRate register = 32 * fXTAL / bps
    w = int(32 * 32_000_000 / bps)
    return bytes([(w>>16)&0xFF,(w>>8)&0xFF,w&0xFF])

def _fdev_word(hz):
    # Fdev register = Fdev_Hz / fXTAL * 2^25
    w = int(hz / 32_000_000 * (1 << 25))
    return bytes([(w>>16)&0xFF,(w>>8)&0xFF,w&0xFF])

def _radio_base_init():
    """Common startup: standby, TCXO, calibrate, regulator, freq, PA."""
    _cmd(bytes([_STANDBY, 0x00]));               time.sleep_ms(5)
    _cmd(bytes([_SET_TCXO, 0x07, 0x00, 0x00, 0x40])); time.sleep_ms(5)
    _cmd(bytes([_STANDBY, 0x01]));               time.sleep_ms(5)
    _cmd(bytes([_CALIBRATE, 0x7F]));             time.sleep_ms(10)
    _cmd(bytes([_CAL_IMAGE, 0x6B, 0x6F]));       time.sleep_ms(5)
    _cmd(bytes([_SET_REGULATOR, 0x01]))
    _cmd(bytes([_SET_RF_FREQ]) + _freq_word(433_500_000))
    # PA: LP path, duty=0x04, hpMax=0x00, devSel=LP(0x01), paLut=0x01
    _cmd(bytes([_SET_PA_CONFIG, 0x04, 0x00, 0x01, 0x01]))
    # -17 dBm (0xEF signed), 200 us ramp
    _cmd(bytes([_SET_TX_PARAMS, 0xEF, 0x04]))
    _cmd(bytes([_SET_BUF_ADDR, 0x00, 0x80]))
    _cmd(bytes([_SET_DIO_IRQ, 0x00, 0x03, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00]))

def _send(payload, wait_ms):
    """Load payload into FIFO, trigger TX, wait, return to standby."""
    _cmd(bytes([_CLR_IRQ, 0xFF, 0xFF]))
    _cmd(bytes([_WRITE_BUF, 0x00]) + payload)
    _ant_tx_lp()
    _cmd(bytes([_SET_TX, 0x00, 0x00, 0x00]))
    time.sleep_ms(wait_ms)
    _cmd(bytes([_STANDBY, 0x01]))
    _ant_off()

# =============================================================================
# Mode 1 - LoRa
# SF7, BW 125 kHz, CR 4/5, explicit header, CRC on, 10-byte payload
# Air time ~41 ms/packet
# =============================================================================

def init_lora():
    _radio_base_init()
    _cmd(bytes([_SET_PKT_TYPE, PKT_LORA]))
    # SF=7, BW=0x04(125kHz), CR=0x01(4/5), LowDataOpt=0x00
    _cmd(bytes([_SET_MOD_PARAMS, 0x07, 0x04, 0x01, 0x00]))
    # PreambleLen=8, ExplicitHdr, Payload=10, CRC=on, IQ=normal
    _cmd(bytes([_SET_PKT_PARAMS, 0x00, 0x08, 0x00, 0x0A, 0x01, 0x00]))
    print("[INIT] LoRa  SF7 BW125 CR4/5 @ 433.500 MHz  -17 dBm")

def tx_lora(n):
    _send(b"LR433:" + n.to_bytes(4, "big"), 60)
    print("  [LoRa #{:04d}]".format(n))

# =============================================================================
# Mode 2 - GFSK
# 9600 bps, Gaussian BT=0.5, Fdev=5 kHz, fixed 10-byte payload
# Air time ~16 ms/packet
# =============================================================================

def init_gfsk():
    _radio_base_init()
    _cmd(bytes([_SET_PKT_TYPE, PKT_GFSK]))
    _cmd(bytes([_SET_MOD_PARAMS])
         + _bitrate_word(9600)
         + bytes([SHAPE_BT05])   # BT=0.5
         + bytes([0x0D])         # RxBW 29.3 kHz
         + _fdev_word(5000))     # Fdev 5 kHz
    _cmd(bytes([_SET_PKT_PARAMS,
                0x00,0x20,0x05,0x18,0x00,0x01,0x0A,0x02,0x00]))
    print("[INIT] GFSK  9600bps BT=0.5 Fdev=5kHz @ 433.500 MHz  -17 dBm")

def tx_gfsk(n):
    _send(b"GF433:" + n.to_bytes(4, "big"), 30)
    print("  [GFSK #{:04d}]".format(n))

# =============================================================================
# Mode 3 - GMSK  (natively supported: STM32WL55 datasheet lists (G)MSK)
#
# GMSK = GFSK with modulation index h = 0.5 AND Gaussian filter BT = 0.3
#   h = 2 * Fdev / Bitrate = 0.5  =>  Fdev = Bitrate / 4
#   9600 bps => Fdev = 2400 Hz
#   BT = 0.3 is the standard (used in GSM, NB-IoT, TETRA)
#
# Air time ~16 ms/packet
# =============================================================================

def init_gmsk():
    _radio_base_init()
    _cmd(bytes([_SET_PKT_TYPE, PKT_GFSK]))
    _cmd(bytes([_SET_MOD_PARAMS])
         + _bitrate_word(9600)
         + bytes([SHAPE_BT03])   # BT=0.3  <- key GMSK difference vs GFSK
         + bytes([0x0D])         # RxBW 29.3 kHz
         + _fdev_word(2400))     # Fdev = Bitrate/4 = 2400 Hz  (h=0.5)
    _cmd(bytes([_SET_PKT_PARAMS,
                0x00,0x20,0x05,0x18,0x00,0x01,0x0A,0x02,0x00]))
    print("[INIT] GMSK  9600bps BT=0.3 h=0.5 Fdev=2400Hz @ 433.500 MHz  -17 dBm")

def tx_gmsk(n):
    _send(b"GM433:" + n.to_bytes(4, "big"), 30)
    print("  [GMSK #{:04d}]".format(n))

# =============================================================================
# Mode 4 - BPSK  (Differential BPSK, Sigfox-style)
# 100 bps, DBPSK pulse shaping, 12-byte payload
# Air time ~1.5 s/packet
# =============================================================================

def init_bpsk():
    _radio_base_init()
    _cmd(bytes([_SET_PKT_TYPE, PKT_BPSK]))
    # BitRate 100 bps: 32*32e6/100 = 10240000 = 0x9C4000
    # PulseShape=0x16 (DBPSK Sigfox standard ramp)
    _cmd(bytes([_SET_MOD_PARAMS, 0x9C, 0x40, 0x00, 0x16]))
    # Payload=12 bytes, ramp=0x20
    _cmd(bytes([_SET_PKT_PARAMS, 0x00, 0x0C, 0x20]))
    print("[INIT] BPSK  100bps DBPSK @ 433.500 MHz  -17 dBm  (~1.5s/pkt)")

def tx_bpsk(n):
    _send(b"BP433:" + n.to_bytes(4, "big") + b"\x00\x00", 1600)
    print("  [BPSK #{:04d}]".format(n))

# =============================================================================
# Mode 5 - 2-FSK  (plain binary FSK, no Gaussian shaping)
# 9600 bps, Fdev=25 kHz (modulation index h = 2*25000/9600 ~= 5.2)
# No pulse shaping filter - hard frequency transitions (rectangular pulses)
# Air time ~16 ms/packet
# Wider Fdev than GFSK makes it more noise-tolerant but uses more bandwidth
# =============================================================================

# =============================================================================
# Mode 6 - OOK  (simulated via CW carrier toggle)
#
# SX126x / STM32WL55 has no native OOK modulation register.
# Simulation method:
#   Bit=1 (Mark)  -> SetTxContinuousWave (0xD1)  carrier ON
#   Bit=0 (Space) -> SetStandby (0x80, 0x01)      carrier OFF
# toggled at 1000 bps (1000 us per bit).
#
# This produces a genuine OOK RF signal decodable by any SDR or
# envelope detector. PA ramp (~200 us) is < 1 bit period so
# transitions are clean at this bit rate.
#
# Transmitted frame: 3-byte 0xAA preamble + 0xA5 test byte + counter byte
# =============================================================================

_OOK_BIT_US = 1000   # 1000 bps = 1000 us/bit

def _ook_on():
    _ant_tx_lp()
    _cmd(bytes([_SET_TX_CW]))

def _ook_off():
    _cmd(bytes([_STANDBY, 0x01]))
    _ant_off()

def _ook_send_byte(val):
    """Send 8 bits MSB-first via carrier toggle."""
    for i in range(7, -1, -1):
        if (val >> i) & 1:
            _ook_on()
        else:
            _ook_off()
        time.sleep_us(_OOK_BIT_US)
    _ook_off()

def init_ook():
    _radio_base_init()
    # Use GFSK base type - actual modulation is CW toggle, not packet TX
    _cmd(bytes([_SET_PKT_TYPE, PKT_GFSK]))
    _cmd(bytes([_SET_MOD_PARAMS])
         + _bitrate_word(1000)
         + bytes([SHAPE_NONE])   # No pulse shaping for OOK
         + bytes([0x13])         # RxBW 58.6 kHz (wider for OOK envelope)
         + _fdev_word(0))        # No freq deviation
    print("[INIT] OOK   1000bps CW-toggle sim @ 433.500 MHz  -17 dBm")

def tx_ook(n):
    frame = [0xAA, 0xAA, 0xAA,   # preamble
             0xA5,                # test pattern 10100101
             n & 0xFF]            # counter LSB
    for b in frame:
        _ook_send_byte(b)
    time.sleep_ms(5)              # inter-frame gap
    print("  [OOK  #{:04d}] preamble+0xA5+{:#04x}".format(n, n & 0xFF))

# =============================================================================
# Mode 6 - 2-FSK  (plain binary FSK, no Gaussian shaping)
#
# 2-FSK is the simplest digital FM: two discrete frequencies for mark/space.
# No Gaussian filter (SHAPE_NONE) gives hard frequency transitions, producing
# a wider spectrum than GFSK but simpler receivers.
# 4800 bps, Fdev=10 kHz (deviation ratio = 2*Fdev/BR = 4.17 => wideband FSK)
# Air time ~16 ms/packet
# =============================================================================

def init_2fsk():
    _radio_base_init()
    _cmd(bytes([_SET_PKT_TYPE, PKT_GFSK]))
    _cmd(bytes([_SET_MOD_PARAMS])
         + _bitrate_word(4800)
         + bytes([SHAPE_NONE])   # No pulse shaping -> hard FSK transitions
         + bytes([0x0C])         # RxBW = 39.0 kHz  (must cover 2*Fdev + BR/2)
         + _fdev_word(10000))    # Fdev = 10 kHz (wideband, easy to receive)
    _cmd(bytes([_SET_PKT_PARAMS,
                0x00,0x20,0x05,0x18,0x00,0x01,0x0A,0x02,0x00]))
    print("[INIT] 2-FSK  4800bps no-shaping Fdev=10kHz @ 433.500 MHz  -17 dBm")

def tx_2fsk(n):
    _send(b"2F433:" + n.to_bytes(4, "big"), 30)
    print("  [2FSK #{:04d}]".format(n))

# =============================================================================
# Mode 7 - 4-FSK  (4-level FSK, simulated via per-symbol frequency switching)
#
# The SX126x has only one Fdev register so true 4-FSK is NOT native.
# Simulation: each 2-bit dibit maps to one of four carrier frequencies,
# transmitted as CW bursts via SetRfFrequency + SetTxContinuousWave.
#
# Tone spacing: 5 kHz between adjacent tones (standard M-FSK convention)
# Centre = 433.500 MHz. Four tones:
#   dibit 00 -> 433.5 MHz - 7.5 kHz = 433.4925 MHz
#   dibit 01 -> 433.5 MHz - 2.5 kHz = 433.4975 MHz
#   dibit 10 -> 433.5 MHz + 2.5 kHz = 433.5025 MHz
#   dibit 11 -> 433.5 MHz + 7.5 kHz = 433.5075 MHz
#
# Symbol rate: 2400 baud (each symbol = 2 bits => 4800 bps effective data rate)
# Symbol period: 1000/2400 baud = 416 us
#
# This is a real 4-FSK RF signal — any SDR with 4-FSK demodulator will work.
# =============================================================================

# Pre-compute the four 4-byte frequency words  (avoids runtime division in loop)
_4FSK_FREQS = [
    _freq_word(433_492_500),   # 00  centre - 7.5 kHz
    _freq_word(433_497_500),   # 01  centre - 2.5 kHz
    _freq_word(433_502_500),   # 10  centre + 2.5 kHz
    _freq_word(433_507_500),   # 11  centre + 7.5 kHz
]
_4FSK_SYM_US = 416   # symbol period in us at 2400 baud

def _4fsk_send_symbol(dibit):
    """Transmit one 4-FSK symbol (0-3) as a CW burst at the mapped frequency."""
    _cmd(bytes([_SET_RF_FREQ]) + _4FSK_FREQS[dibit & 0x03])
    _ant_tx_lp()
    _cmd(bytes([_SET_TX_CW]))
    time.sleep_us(_4FSK_SYM_US)
    _cmd(bytes([_STANDBY, 0x01]))
    _ant_off()

def _4fsk_send_byte(val):
    """Split one byte into 4 dibits (MSB first) and transmit each as a symbol."""
    for shift in (6, 4, 2, 0):
        _4fsk_send_symbol((val >> shift) & 0x03)

def init_4fsk():
    _radio_base_init()
    # Use GFSK packet type as base — actual transmission uses CW per symbol
    _cmd(bytes([_SET_PKT_TYPE, PKT_GFSK]))
    _cmd(bytes([_SET_MOD_PARAMS])
         + _bitrate_word(2400)
         + bytes([SHAPE_NONE])
         + bytes([0x0C])         # RxBW 39 kHz (covers all 4 tones)
         + _fdev_word(0))
    print("[INIT] 4-FSK  2400baud 4-tone 5kHz-spacing @ 433.500 MHz  -17 dBm  [simulated]")

def tx_4fsk(n):
    # Frame: 2-byte preamble 0xAA, 6-byte tag, 2-byte counter = 10 bytes
    frame = [0xAA, 0xAA] + list(b"4F433:") + list(n.to_bytes(2, "big"))
    for b in frame:
        _4fsk_send_byte(b)
    time.sleep_ms(5)   # inter-frame gap
    print("  [4FSK #{:04d}] {} symbols".format(n, len(frame) * 4))

# =============================================================================
# Menu + runner
# =============================================================================

MODES = [
    ("LoRa",  init_lora,  tx_lora),
    ("GFSK",  init_gfsk,  tx_gfsk),
    ("GMSK",  init_gmsk,  tx_gmsk),
    ("BPSK",  init_bpsk,  tx_bpsk),
    ("OOK",   init_ook,   tx_ook),
    ("2-FSK", init_2fsk,  tx_2fsk),
    ("4-FSK", init_4fsk,  tx_4fsk),
]

def show_menu():
    print("\n" + "=" * 60)
    print("  NUCLEO-WL55 Multi-Mode TX @ 433.5 MHz  -17 dBm")
    print("=" * 60)
    print("  1) LoRa   SF7 BW125 CR4/5         ~41ms/pkt   [native]")
    print("  2) GFSK   9600bps BT=0.5 Fdev5k   ~16ms/pkt   [native]")
    print("  3) GMSK   9600bps BT=0.3 h=0.5    ~16ms/pkt   [native]")
    print("  4) BPSK   100bps DBPSK             ~1.5s/pkt   [native]")
    print("  5) OOK    1000bps CW-toggle        ~40ms/frame [simulated]")
    print("  6) 2-FSK  4800bps no-shape Fdev10k ~16ms/pkt   [native]")
    print("  7) 4-FSK  2400baud 4-tone 5kHz-sp  ~17ms/frame [simulated]")
    print("  8) ALL    cycle each for 10 s")
    print("=" * 60)

def run_mode(name, init_fn, tx_fn, ms=10_000):
    print("\n>>> {} - {} s <<<".format(name, ms // 1000))
    init_fn()
    led = pyb.LED(1)
    n = 0
    t_end = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(t_end, time.ticks_ms()) > 0:
        tx_fn(n)
        led.toggle()
        n += 1
    _ant_off()
    _cmd(bytes([_STANDBY, 0x01]))
    print(">>> {} done - {} pkts <<<".format(name, n))

def main():
    show_menu()
    c = input("Select [1-8]: ").strip()
    if c == "1":
        while True:
            run_mode(*MODES[0])
    elif c == "2":
        while True:
            run_mode(*MODES[1])
    elif c == "3":
        while True:
            run_mode(*MODES[2])
    elif c == "4":
        while True:
            run_mode(*MODES[3])
    elif c == "5":
        while True:
            run_mode(*MODES[4])
    elif c == "6":
        while True:
            run_mode(*MODES[5])
    elif c == "7":
        while True:
            run_mode(*MODES[6])
    else:
        print("\nCycling ALL modes 10s each. Ctrl-C to stop.\n")
        while True:
            for name, init_fn, tx_fn in MODES:
                run_mode(name, init_fn, tx_fn, 10_000)

if __name__ == "__main__":
    main()
