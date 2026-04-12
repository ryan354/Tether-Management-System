---
type: community
cohesion: 0.10
members: 25
---

# FastAPI Core & Config

**Cohesion:** 0.10 - loosely connected
**Members:** 25 nodes

## Members
- [[.set_controller_config()]] - code - app\main.py
- [[BaseModel]] - code
- [[ControllerConfig]] - code - app\main.py
- [[Get current configuration]] - rationale - app\main.py
- [[List available serial ports]] - rationale - app\main.py
- [[MotorData]] - code - app\main.py
- [[Reset encoder counter (tether or launcher)]] - rationale - app\main.py
- [[Sync encoder invert flags from config.]] - rationale - app\main.py
- [[Toggle pauseresume - STOP immediately (PWM=1000), resume from saved targets]] - rationale - app\main.py
- [[Update Trapezoidal + FF+P controller parameters.]] - rationale - app\main.py
- [[_apply_encoder_invert()]] - code - app\main.py
- [[get_config()]] - code - app\main.py
- [[get_encoder_status()]] - code - app\main.py
- [[get_info()]] - code - app\main.py
- [[get_motor_status()]] - code - app\main.py
- [[list_serial_ports()]] - code - app\main.py
- [[main.py]] - code - app\main.py
- [[pause_resume_motor()]] - code - app\main.py
- [[reset_encoder()]] - code - app\main.py
- [[root()]] - code - app\main.py
- [[save_config()]] - code - app\main.py
- [[set_config()]] - code - app\main.py
- [[set_controller()]] - code - app\main.py
- [[startup_event()]] - code - app\main.py
- [[stop_motor()]] - code - app\main.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/FastAPI_Core_&_Config
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_USBL Fold Mechanism]]
- 8 edges to [[_COMMUNITY_Motor PWM Control]]

## Top bridge nodes
- [[main.py]] - degree 29, connects to 2 communities
- [[set_config()]] - degree 8, connects to 2 communities
- [[.set_controller_config()]] - degree 3, connects to 1 community
- [[stop_motor()]] - degree 2, connects to 1 community