# mmWave Radar Station

**HearthSense is a camera-free mmWave radar research prototype for observing indoor movement and investigating fall-like activity.**

> **Status (November 2026):** offline Python prototype available. Hardware integration and experimental results are pending. This project is **not** a validated fall-detection or emergency response device.

## Project scope

This repository documents the **standalone radar project** being developed for Hack Club Fabricate: an adjustable 60 GHz radar sensing station capable of collecting, visualising and analysing human-motion measurements in a controlled indoor environment.

The objective is to investigate whether radar point-cloud and tracked-object data can distinguish everyday movement from *fall-like events*, particularly near the floor and under different mounting conditions.

## Bill of materials (Fabricate)

**[Download the root-level BOM.csv](BOM.csv)** — itemised costs in USD, matching the latest radar-only Fabricate BOM shared for this project. Links point to the manufacturer or Australian retailers.

| Part | Qty | Unit cost (USD) | Line total (USD) | Funding | Supplier |
| --- | ---: | ---: | ---: | --- | --- |
| [TI IWR6843ISK-ODS radar](https://www.ti.com/tool/IWR6843ISK-ODS) | 1 | $235.55 | $235.55 | Grant | Texas Instruments |
| [Raspberry Pi 5 Model B 8GB](https://core-electronics.com.au/raspberry-pi-5-model-b-8gb.html) | 1 | $191.25 | $191.25 | Grant | Core Electronics |
| [Raspberry Pi 5 Active Cooler](https://core-electronics.com.au/raspberry-pi-5-active-cooler.html) | 1 | $6.00 | $6.00 | Grant | Core Electronics |
| [Official Raspberry Pi 5 27W USB-C power supply](https://core-electronics.com.au/raspberry-pi-5-power-supply-usb-c-pd-27w-white.html) | 1 | $14.20 | $14.20 | Grant | Core Electronics |
| Shipping, VAT, taxes and contingency | 1 | $36.80 | $36.80 | Grant | Provisional allowance |
| 3D-printed casings (self-supplied) | 1 | $0.00 | $0.00 | Already owned | Self-supplied |
| [Kingston Canvas Select Plus 64GB microSD card](https://www.umart.com.au/product/kingston-canvas-select-plus-64gb-100mb-s-microsd-card-with-adapter-sdcs3-64gb-89541) | 1 | $16.20 | $16.20 | Grant | Umart |
| **Total** | | | **$500.00** | | |

**Proposed grant-funded total: US$500.00.** The US$36.80 line is a provisional allowance for shipping, taxes and incidental order costs, **not an incurred expense**. Actual charges should be reconciled against receipts and the Fabricate BOM.

The 3D-printed mounting assembly and housings are original fabrication deliverables, made using existing resources. These are budgeted/proposed purchases, **not claims of completed fabrication or supplier stock availability**. Boot storage is included in the BOM through the Kingston 64GB microSD card. Check that necessary USB data cables are available or included with the ordered hardware.

## Engineering objectives

1. **Radar acquisition:** bring up the TI radar development board, inspect supported tracking demonstrations and capture timestamped point-cloud / track output.
2. **Mechanical design:** model and fabricate a secure radar housing and adjustable mounting bracket, with cable strain relief and unobstructed radar aperture.
3. **Mounting study:** compare overhead and high-wall arrangements, recording sensor height, tilt, tracked region and visibility near the floor.
4. **Activity experiments:** collect data for walking, sitting, bending, kneeling and lying down, as well as safely simulated fall-like transitions.
5. **Prototype classification:** explore interpretable radar-derived features and basic classification; distinguish fall-like events from confounding daily activities.
6. **Evaluation:** report event recall, false-alarm frequency, latency, tracking dropouts and sensitivity to furniture and placement changes.

Results will be reported only after experimental validation. Avoid leakage between overlapping windows from the same recording session when evaluating models.

 ## HearthSense software

The HearthSense V0.2 Python prototype captures UART data and provides offline replay, a 3D viewer and an **experimental fall-like activity demonstrator**. The board and Raspberry Pi integration are pending.

| Path | Role |
| --- | --- |
| `radar/acquisition.py` | Discovers serial ports, optionally sends a TI configuration, and records the raw stream. |
| `radar/packets.py`, `radar/decoder.py` | Define the wire format and decode incremental byte streams into immutable frames. |
| `radar/replay.py` | Produces timestamped frames from indexed captures, bare UART files, or a deterministic synthetic trajectory. |
| `processing/features.py`, `processing/detector.py` | Extract per-track motion and height features and apply the demonstration rules. |
| `visualisation/viewer.py` | Shows the point cloud, track IDs, speeds, height estimates, frame information and event annotations. |
| `tests/` | Tests the UART wire format, recording, replay, features, detector and static rendering offline. |

### Install and run offline

Use Python 3.11 or newer. These commands use PowerShell from the repository root. On Raspberry Pi OS, create the environment with `python3 -m venv .venv` and activate it with `source .venv/bin/activate`.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m pytest -q
hearthsense replay --synthetic
hearthsense view --synthetic
hearthsense view --synthetic --save hearthsense-demo.png
```

The window needs a Matplotlib GUI backend. For a headless machine, set `MPLBACKEND=Agg` in the environment and use `--save` to render the last frame. The offline suite passed on Windows with CPython 3.12. It uses generated UART frames, mocked serial I/O and headless rendering. The synthetic stream contains 60 frames and produces one demonstration event.

### Capture and replay

Use `hearthsense ports` to identify the data and control interfaces. Substitute the port names and baud rates for the loaded firmware. The values below are examples. Use a new folder for each capture.

```powershell
hearthsense record recordings/run01 --data-port COM7 --data-baud 921600 --duration 30
hearthsense record recordings/run02 --data-port COM7 --data-baud 921600 --control-port COM6 --control-baud 115200 --config ods.cfg
hearthsense replay recordings/run01
hearthsense view recordings/run01
hearthsense replay recordings/run01/data.bin --frame-period 0.1
```

With no configuration file, start the firmware stream separately. With `--config`, the recorder expects a TI `Done` acknowledgement for each command. Ctrl+C closes the serial connections and finalises the index. Stopping the host capture leaves the radar's firmware state as configured.

Each recording contains `data.bin` and `index.jsonl`. The index records UTC start time, port settings, the optional configuration filename and SHA-256, monotonic read times, byte offsets, and completion status. A frame inherits the host timestamp of the read that completed it. Several frames can therefore share a timestamp. Use `--frame-period` when the configured output cadence is known. This spaces decoded frames uniformly and compresses any gaps due to dropped frames. A bare UART stream requires `--frame-period` because it has no host timing index.

### Protocol and processing assumptions

- The decoder uses the 40-byte little-endian frame header and recognises TLVs 1010, 1011, 1012, 1020 and 1021. It bounds packet length, checks TLV boundaries and record sizes, accepts unpadded frames or 32-byte alignment padding, and reports recovery statistics. It records unknown TLV type IDs and skips their payloads. TLV headers are validated as bytes arrive, and a sync pattern within a structurally plausible frame cannot interrupt it. A plausible corrupted length can delay recovery until the size limit for that candidate is reached or replay reaches EOF. At EOF, replay reports truncated candidates and scans for any remaining complete frames. The documented header provides no checksum, so structural checks cannot detect every corrupted byte or resolve every ambiguous stream.
- The [TI UART Format Guide](https://dev.ti.com/tirex/explore/content/radar_toolbox_4_00_00_05/software_docs/Understanding_UART_Data_Output_Format.html) specifies payload-only TLV lengths, 12-byte height records with a 32-bit track ID, and unsigned range and SNR. The [TI Overhead 3D People Tracking Guide](https://dev.ti.com/tirex/explore/content/radar_toolbox_4_00_00_05/source/ti/examples/Industrial_and_Personal_Electronics/People_Tracking/Overhead_3D_People_Tracking/docs/overhead_3d_people_tracking_user_guide.html) describes some of these differently. The parser defaults follow the UART guide and agree with the TI Visualizer parser inspected in a public mirror. `--tlv-length inclusive` selects the documented header-inclusive length convention explicitly.
- Points are converted from spherical coordinates with boresight along +Y. The viewer plots points in sensor coordinates and tracks as delivered by firmware. Verify their alignment for the mounting configuration. Target indices refer to points in the previous frame and are preserved as raw byte IDs, including the firmware's reserved values.
- Recorded-data detection requires `--room-z` after verifying track position, speed and height share a room frame with the floor at Z=0 and +Z pointing up. The rules look for descent, a substantial drop, and sustained low position with little movement. Height helps when available. Missing tracks, duplicate or out-of-order timestamps, non-consecutive frame numbers and observation gaps reset continuity. Frame continuity is checked per subframe with unsigned 32-bit wraparound. Onset requires a minimum descent rate and a cumulative drop within a time window, so the drop threshold does not depend on frame rate. Post-event stillness checks both reported velocity and position-derived speed. Rule thresholds are demonstration values. A future Random Forest can use the `ActivityDetector` interface and the same feature stream.
- Implementation and tests were developed with AI assistance. TI firmware, configuration files and Visualizer source are distributed separately under TI's terms.

### Hardware integration milestones

1. Load an Overhead 3D People Tracking image and matching configuration from TI for the IWR6843ISK-ODS. Identify the UART interfaces, permissions and baud rates on the Raspberry Pi.
2. Capture a short stream and compare frame counts, TLV layouts, track IDs, axes and height with the TI Visualizer. Measure packet loss and confirm whether capture timestamps are adequate for motion features.
3. Verify the coordinate transform for the actual mounting height and tilt. Collect consented, labelled recordings for ordinary activities and carefully controlled fall-like movement. Assess false alarms, latency and missed events before considering a trained classifier.

## Software and references

- [TI IWR6843ISK-ODS](https://www.ti.com/tool/IWR6843ISK-ODS)
- [TI Radar Toolbox](https://www.ti.com/tool/RADAR-TOOLBOX)
- [Raspberry Pi documentation](https://www.raspberrypi.com/documentation/)

## Safety and privacy

This is experimental human-activity research, **not** clinical fall detection. Do not rely on its output for emergency assistance. Obtain participant consent, use safe controlled test procedures and avoid publishing identifiable recordings or personal data.

## License

This repository includes an [MIT License](LICENSE). Review licensing separately for any future hardware design files and research datasets.
