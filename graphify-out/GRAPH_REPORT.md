# Graph Report - .  (2026-04-12)

## Corpus Check
- Corpus is ~4,912 words - fits in a single context window. You may not need a graph.

## Summary
- 125 nodes · 168 edges · 10 communities detected
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 8 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_FastAPI Core & Config|FastAPI Core & Config]]
- [[_COMMUNITY_Encoder Serial Interface|Encoder Serial Interface]]
- [[_COMMUNITY_USBL Fold Mechanism|USBL Fold Mechanism]]
- [[_COMMUNITY_Motor PWM Control|Motor PWM Control]]
- [[_COMMUNITY_Hardware Documentation|Hardware Documentation]]
- [[_COMMUNITY_Web App & Dependencies|Web App & Dependencies]]
- [[_COMMUNITY_Motion Control & Feedback|Motion Control & Feedback]]
- [[_COMMUNITY_Setup Script|Setup Script]]
- [[_COMMUNITY_Logging (Loguru)|Logging (Loguru)]]
- [[_COMMUNITY_Data Validation (Pydantic)|Data Validation (Pydantic)]]

## God Nodes (most connected - your core abstractions)
1. `EncoderReader` - 13 edges
2. `FoldMotor` - 12 edges
3. `Motor` - 10 edges
4. `set_pwm()` - 8 edges
5. `set_config()` - 8 edges
6. `PCA9685 PWM Controller` - 5 edges
7. `_apply_encoder_invert()` - 4 edges
8. `Feedforward-P Speed Controller` - 4 edges
9. `FastAPI Server (main.py)` - 4 edges
10. `crc16()` - 3 edges

## Surprising Connections (you probably didn't know these)
- `fastapi (Python Package)` --references--> `FastAPI Server (main.py)`  [INFERRED]
  app/requirements.txt → README.md
- `FastAPI Server (main.py)` --references--> `uvicorn (Python Package)`  [INFERRED]
  README.md → app/requirements.txt
- `Encoder Module (encoder.py)` --references--> `pyserial (Python Package)`  [INFERRED]
  README.md → app/requirements.txt
- `REST API (v1.0)` --references--> `fastapi-versioning (Python Package)`  [INFERRED]
  README.md → app/requirements.txt
- `CLAUDE.md Graphify Config` --references--> `Tether Management System`  [EXTRACTED]
  CLAUDE.md → README.md

## Hyperedges (group relationships)
- **Motor Speed Control Loop** — readme_trapezoidal_velocity_profile, readme_ff_p_controller, readme_rs485_modbus_encoder, readme_pca9685 [EXTRACTED 0.95]
- **USBL Fold Mechanism System** — readme_usbl_fold_motor, readme_fold_limit_switches, readme_usbl_fold_mechanism [EXTRACTED 0.95]
- **Web Application Stack** — readme_fastapi_server, readme_rest_api, readme_web_ui, requirements_fastapi, requirements_uvicorn [EXTRACTED 0.90]

## Communities

### Community 0 - "FastAPI Core & Config"
Cohesion: 0.1
Nodes (19): BaseModel, _apply_encoder_invert(), ControllerConfig, get_config(), list_serial_ports(), MotorData, pause_resume_motor(), Sync encoder invert flags from config. (+11 more)

### Community 1 - "Encoder Serial Interface"
Cohesion: 0.12
Nodes (12): build_request(), crc16(), EncoderReader, init_encoder(), parse_response(), Reset counter for specific encoder, Get all encoder statuses, Get named status dictionary (+4 more)

### Community 2 - "USBL Fold Mechanism"
Cohesion: 0.12
Nodes (14): fold_mount(), FoldMotor, get_fold_status(), Set PWM value for channel (0-4095), Simple motor controller for fold/unfold mechanism with limit switches., Load fold motor PWM settings from CONFIG., Set direct PWM value (700-1300). Set to -1 to disable direct mode., Unfold the USBL mount. (+6 more)

### Community 3 - "Motor PWM Control"
Cohesion: 0.11
Nodes (13): enable_pwm(), get_all_motors_status(), load_config(), Motor, Invert PWM around neutral (1000). 850->1150, 1150->850, etc., Step current toward target by at most accel/decel_rate per cycle., Trapezoidal + FF+P controller -> RC PWM (700-1300).          Stage 1 - Length, Update motor state with encoder feedback and compute PWM. (+5 more)

### Community 4 - "Hardware Documentation"
Cohesion: 0.18
Nodes (12): CLAUDE.md Graphify Config, Direct PWM Mode, Fold/Unfold Limit Switches, Launcher Reel Motor, Navigator Board (Blue Robotics), PCA9685 PWM Controller, Raspberry Pi, Rationale: 30s Safety Timeout for Fold (+4 more)

### Community 5 - "Web App & Dependencies"
Cohesion: 0.22
Nodes (9): config.json (Persistent Config), FastAPI Server (main.py), REST API (v1.0), setup.sh Installer, motor-control systemd Service, Web UI, fastapi (Python Package), fastapi-versioning (Python Package) (+1 more)

### Community 6 - "Motion Control & Feedback"
Cohesion: 0.33
Nodes (7): Direction Inversion Feature, Encoder Module (encoder.py), Feedforward-P Speed Controller, Rationale: Trapezoidal + FF-P Control, RS485 Modbus RTU Encoder, Trapezoidal Velocity Profile, pyserial (Python Package)

### Community 7 - "Setup Script"
Cohesion: 1.0
Nodes (0): 

### Community 8 - "Logging (Loguru)"
Cohesion: 1.0
Nodes (1): loguru (Python Package)

### Community 9 - "Data Validation (Pydantic)"
Cohesion: 1.0
Nodes (1): pydantic (Python Package)

## Knowledge Gaps
- **40 isolated node(s):** `Thread-safe encoder reader with Modbus RTU`, `Start encoder reading thread`, `Stop encoder reading thread`, `Initialize serial connection`, `Reset counter for specific encoder` (+35 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Setup Script`** (1 nodes): `setup.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Logging (Loguru)`** (1 nodes): `loguru (Python Package)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Data Validation (Pydantic)`** (1 nodes): `pydantic (Python Package)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Motor` connect `Motor PWM Control` to `FastAPI Core & Config`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `FoldMotor` connect `USBL Fold Mechanism` to `FastAPI Core & Config`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `set_pwm()` connect `USBL Fold Mechanism` to `FastAPI Core & Config`, `Motor PWM Control`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **What connects `Thread-safe encoder reader with Modbus RTU`, `Start encoder reading thread`, `Stop encoder reading thread` to the rest of the system?**
  _40 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `FastAPI Core & Config` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._
- **Should `Encoder Serial Interface` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._
- **Should `USBL Fold Mechanism` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._