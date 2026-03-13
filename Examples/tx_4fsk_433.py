# =============================================================================
# 4-FSK Transmitter (simulated) — NUCLEO-WL55 @ 433.5 MHz
#
# The SX126x has only one Fdev register so true 4-FSK is NOT native.
# Simulation: each 2-bit dibit maps to one of four CW carrier frequencies,
# transmitted as short CW bursts via SetRfFrequency + SetTxContinuousWave.
#
# Tone map (5 kHz spacing, Grey-coded):
#   dibit 00 -> 433.492500 MHz  (centre - 7.5 kHz)
#   dibit 01 -> 433.497500 MHz  (centre - 2.5 kHz)
#   dibit 10 -> 433.502500 MHz  (centre + 2.5 kHz)
#   dibit 11 -> 433.507500 MHz  (centre + 7.5 kHz)
#
# Symbol rate: 2400 baud  =>  4800 bps effective data rate
# Symbol period: ~416 us
# Upload: mpremote cp tx_4fsk_433.py :main.py && mpremote reset
# =============================================================================

import time
import pyb
from machine import SPI, Pin
import stm

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
_SET_DIO_IRQ    = 0x08
_SET_TX_CW      = 0xD1

_SYM_US = 416   # symbol period at 2400 baud

_ctrl1 = Pin("FE_CTRL1", Pin.OUT, value=0)
_ctrl2 = Pin("FE_CTRL2", Pin.OUT, value=0)
_ctrl3 = Pin("FE_CTRL3", Pin.OUT, value=0)
_spi   = SPI("SUBGHZ")

def _cmd(b):
    stm.subghz_cs(False); _spi.write(b); stm.subghz_cs(True)

def _ant_tx_lp():
    _ctrl1.value(1); _ctrl2.value(1); _ctrl3.value(0)

def _ant_off():
    _ctrl1.value(0); _ctrl2.value(0); _ctrl3.value(0)

def _freq_word(hz):
    w = int(hz / 32_000_000 * (1 << 25))
    return bytes([(w>>24)&0xFF,(w>>16)&0xFF,(w>>8)&0xFF,w&0xFF])

# Pre-computed tone frequency words (avoids division inside hot loop)
_TONES = [
    _freq_word(433_492_500),   # dibit 00
    _freq_word(433_497_500),   # dibit 01
    _freq_word(433_502_500),   # dibit 10
    _freq_word(433_507_500),   # dibit 11
]

def _base_init():
    _cmd(bytes([_STANDBY, 0x00]));                  time.sleep_ms(5)
    _cmd(bytes([_SET_TCXO, 0x07, 0x00, 0x00, 0x40])); time.sleep_ms(5)
    _cmd(bytes([_STANDBY, 0x01]));                  time.sleep_ms(5)
    _cmd(bytes([_CALIBRATE, 0x7F]));                time.sleep_ms(10)
    _cmd(bytes([_CAL_IMAGE, 0x6B, 0x6F]));          time.sleep_ms(5)
    _cmd(bytes([_SET_REGULATOR, 0x01]))
    _cmd(bytes([_SET_RF_FREQ]) + _freq_word(433_500_000))
    _cmd(bytes([_SET_PA_CONFIG, 0x04, 0x00, 0x01, 0x01]))
    _cmd(bytes([_SET_TX_PARAMS, 0xEF, 0x04]))       # -17 dBm
    _cmd(bytes([_SET_BUF_ADDR, 0x00, 0x80]))
    _cmd(bytes([_SET_DIO_IRQ, 0x00, 0x03, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00]))

def _send_symbol(dibit):
    """Transmit one 4-FSK symbol as a CW burst at the mapped frequency."""
    _cmd(bytes([_SET_RF_FREQ]) + _TONES[dibit & 0x03])
    _ant_tx_lp()
    _cmd(bytes([_SET_TX_CW]))
    time.sleep_us(_SYM_US)
    _cmd(bytes([_STANDBY, 0x01]))
    _ant_off()

def _send_byte(val):
    """Split byte into 4 dibits MSB-first and transmit each as a symbol."""
    for shift in (6, 4, 2, 0):
        _send_symbol((val >> shift) & 0x03)

def init():
    _base_init()
    # GFSK base type — actual TX uses CW per symbol, not packet mode
    _cmd(bytes([_SET_PKT_TYPE, 0x00]))
    w = int(32 * 32_000_000 / 2400)                # bitrate word 2400 baud
    _cmd(bytes([_SET_MOD_PARAMS,
                (w>>16)&0xFF, (w>>8)&0xFF, w&0xFF,
                0x00, 0x0C, 0x00, 0x00, 0x00]))
    print("4-FSK ready: 2400baud 4-tone 5kHz-spacing @ 433.500 MHz  -17 dBm  [simulated]")

def main():
    init()
    led = pyb.LED(1)
    n = 0
    print("Transmitting 4-FSK frames continuously (Ctrl-C to stop)")
    while True:
        # Frame: 2-byte preamble + 6-byte tag + 2-byte counter = 10 bytes
        frame = [0xAA, 0xAA] + list(b"4F433:") + list(n.to_bytes(2, "big"))
        for b in frame:
            _send_byte(b)
        time.sleep_ms(5)   # inter-frame gap
        syms = len(frame) * 4
        print("[TX #{:04d}] {} symbols ({} bytes)".format(n, syms, len(frame)))
        led.toggle()
        n += 1

if __name__ == "__main__":
    main()
