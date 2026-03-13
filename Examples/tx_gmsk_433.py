# =============================================================================
# GMSK Transmitter — NUCLEO-WL55 @ 433.5 MHz
# GMSK = GFSK with modulation index h=0.5 and Gaussian filter BT=0.3
#   h = 2*Fdev/Bitrate = 0.5  =>  Fdev = Bitrate/4 = 2400 Hz
#   BT=0.3 is the standard used in GSM, NB-IoT, TETRA
# Native support confirmed in STM32WL55 datasheet ((G)MSK listed)
# 9600 bps, fixed 10-byte payload, air time ~16 ms/packet
# Upload: mpremote cp tx_gmsk_433.py :main.py && mpremote reset
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

def _bitrate_word(bps):
    w = int(32 * 32_000_000 / bps)
    return bytes([(w>>16)&0xFF,(w>>8)&0xFF,w&0xFF])

def _fdev_word(hz):
    w = int(hz / 32_000_000 * (1 << 25))
    return bytes([(w>>16)&0xFF,(w>>8)&0xFF,w&0xFF])

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
    _cmd(bytes([_SET_PKT_TYPE, 0x00]))              # (G)FSK packet type
    _cmd(bytes([_SET_MOD_PARAMS])
         + _bitrate_word(9600)                      # 9600 bps
         + bytes([0x08])                            # Gaussian BT=0.3 (GMSK)
         + bytes([0x0D])                            # RxBW 29.3 kHz
         + _fdev_word(2400))                        # Fdev=Bitrate/4 => h=0.5
    _cmd(bytes([_SET_PKT_PARAMS,
                0x00,0x20,0x05,0x18,0x00,0x01,0x0A,0x02,0x00]))
    print("GMSK ready: 9600bps BT=0.3 h=0.5 Fdev=2400Hz @ 433.500 MHz  -17 dBm")

def main():
    init()
    led = pyb.LED(1)
    n = 0
    print("Transmitting continuously (Ctrl-C to stop)")
    while True:
        payload = b"GM433:" + n.to_bytes(4, "big")  # 10 bytes
        _send(payload, 30)
        print("[TX #{:04d}] {}".format(n, payload))
        led.toggle()
        n += 1

if __name__ == "__main__":
    main()
