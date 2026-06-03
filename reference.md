# ESP8266 NodeMCU → L298N Pin Reference

## Motor Control Wiring

| NodeMCU label | GPIO | L298N pin | Function |
|---|---|---|---|
| D1 | GPIO 5 | IN1 | Left motors — forward direction |
| D2 | GPIO 4 | IN2 | Left motors — reverse direction |
| D5 | GPIO 14 | IN3 | Right motors — forward direction |
| D6 | GPIO 12 | IN4 | Right motors — reverse direction |
| D7 | GPIO 13 | ENA | Left speed (PWM 0–1023) |
| D8 | GPIO 15 | ENB | Right speed (PWM 0–1023) |
| VIN | — | 5V out | NodeMCU logic power from L298N |
| GND | — | GND | Common ground |

## Power Wiring
2× 18650 battery (in series = 7.4V)
→ SPST switch
→ L298N 12V terminal
L298N 5V out → NodeMCU VIN
L298N GND    → NodeMCU GND (common ground)

## Motor Topology
Channel A (IN1/IN2/ENA):
OUT1 → FL motor (+)
OUT1 → RL motor (+)   (both left motors in parallel)
OUT2 → FL motor (-)
OUT2 → RL motor (-)
Channel B (IN3/IN4/ENB):
OUT3 → FR motor (+)
OUT3 → RR motor (+)   (both right motors in parallel)
OUT4 → FR motor (-)
OUT4 → RR motor (-)

## Truth Table

| Motion | IN1 | IN2 | IN3 | IN4 |
|---|---|---|---|---|
| FORWARD | HIGH | LOW | HIGH | LOW |
| REVERSE | LOW | HIGH | LOW | HIGH |
| LEFT | LOW | HIGH | HIGH | LOW |
| RIGHT | HIGH | LOW | LOW | HIGH |
| STOP | LOW | LOW | LOW | LOW |

## Important Notes

- Remove ENA and ENB jumpers from L298N before connecting D7/D8
- Avoid D3 (GPIO0) and D4 (GPIO2) — boot strapping pins
- analogWrite() range on ESP8266: 0–1023 (10-bit)
- SPEED = 700 gives ~68% duty cycle — adjust in firmware if needed
- Motor polarity: if a motor spins wrong way, swap its two wires
  at the L298N output terminal — do not change code