# =============================================================================
# OOK Transmitter (simulated) — NUCLEO-WL55 @ 433.5 MHz
#
# The SX126x / STM32WL55 has NO native OOK modulation.
# Simulation method:
#   Bit=1 (Mark)  -> SetTxContinuousWave (0xD1) -> carrier ON
#   Bit=0 (Space) -> SetStandby          (0x80) -> carrier OFF
# toggled at 1000 bps (1000 us per bit).
#
# Produces a genuine OOK RF signal decodable by any SDR or
# envelope detector. PA ramp (~200 us) < 1 bit period at 1000 bps.
#
# Frame: 3-byte 0xAA preamble + 0xA5 test byte + counter LSB byte
# Upload: mpremote cp tx_ook_433.py :main.py && mpremote reset
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
_SET_TX_CW      = 0xD1   # SetTxContinuousWave

_OOK_BIT_US = 1000       # 1000 bps = 1000 us per bit

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

def _ook_on():
    _ant_tx_lp()
    _cmd(bytes([_SET_TX_CW]))

def _ook_off():
    _cmd(bytes([_STANDBY, 0x01]))
    _ant_off()

def _send_byte(val):
    """Transmit 8 bits MSB-first via carrier toggle."""
    for i in range(7, -1, -1):
        if (val >> i) & 1:
            _ook_on()
        else:
            _ook_off()
        time.sleep_us(_OOK_BIT_US)
    _ook_off()

def init():
    _base_init()
    # GFSK base, no shaping, wide BW — actual TX uses CW toggle not packet mode
    _cmd(bytes([_SET_PKT_TYPE, 0x00]))
    w = int(32 * 32_000_000 / 1000)                # bitrate word for 1000 bps
    _cmd(bytes([_SET_MOD_PARAMS,
                (w>>16)&0xFF, (w>>8)&0xFF, w&0xFF, # BitRate
                0x00,                               # No pulse shaping
                0x13,                               # RxBW 58.6 kHz
                0x00, 0x00, 0x00]))                 # Fdev=0
    print("OOK ready: 1000bps CW-toggle sim @ 433.500 MHz  -17 dBm  [simulated]")

def main():
    init()
    led = pyb.LED(1)
    n = 0
    print("Transmitting OOK frames continuously (Ctrl-C to stop)")
    while True:
        frame = [0xAA, 0xAA, 0xAA,   # 3-byte alternating preamble
                 0xA5,                # test pattern 10100101
                 n & 0xFF]            # counter LSB
        for b in frame:
            _send_byte(b)
        time.sleep_ms(5)              # inter-frame gap
        print("[TX #{:04d}] preamble+0xA5+{:#04x}".format(n, n & 0xFF))
        led.toggle()
        n += 1

if __name__ == "__main__":
    main()
