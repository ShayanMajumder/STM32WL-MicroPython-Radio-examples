# =============================================================================
# BPSK Transmitter — NUCLEO-WL55 @ 433.5 MHz
# Differential BPSK (DBPSK), Sigfox-style, 100 bps
# 12-byte payload, air time ~1.5 s/packet
# Upload: mpremote cp tx_bpsk_433.py :main.py && mpremote reset
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
_WRITE_BUF      = 0x0E
_SET_DIO_IRQ    = 0x08
_CLR_IRQ        = 0x02
_SET_TX         = 0x83

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

def _send(payload, wait_ms):
    _cmd(bytes([_CLR_IRQ, 0xFF, 0xFF]))
    _cmd(bytes([_WRITE_BUF, 0x00]) + payload)
    _ant_tx_lp()
    _cmd(bytes([_SET_TX, 0x00, 0x00, 0x00]))
    time.sleep_ms(wait_ms)
    _cmd(bytes([_STANDBY, 0x01]))
    _ant_off()

def init():
    _base_init()
    _cmd(bytes([_SET_PKT_TYPE, 0x03]))              # BPSK
    # BitRate 100 bps: 32*32e6/100 = 10240000 = 0x9C4000
    # PulseShape 0x16 = DBPSK Sigfox standard ramp
    _cmd(bytes([_SET_MOD_PARAMS, 0x9C, 0x40, 0x00, 0x16]))
    # Payload=12 bytes, ramp=0x20
    _cmd(bytes([_SET_PKT_PARAMS, 0x00, 0x0C, 0x20]))
    print("BPSK ready: 100bps DBPSK @ 433.500 MHz  -17 dBm  (~1.5s/pkt)")

def main():
    init()
    led = pyb.LED(1)
    n = 0
    print("Transmitting continuously (Ctrl-C to stop)")
    while True:
        # 12-byte payload: tag(6) + counter(4) + padding(2)
        payload = b"BP433:" + n.to_bytes(4, "big") + b"\x00\x00"
        _send(payload, 1600)
        print("[TX #{:04d}] {}".format(n, payload))
        led.toggle()
        n += 1

if __name__ == "__main__":
    main()
