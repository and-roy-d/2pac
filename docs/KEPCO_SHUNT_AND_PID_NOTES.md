# Kepco Magnet Programming Shunt Resistor & PID Configuration Notes

> **Purpose**: Reference guide for hardware shunt resistor configurations, Lake Shore 370 output ranges, and software PID settings between **2PAC** and **KPAC**. Consult this document whenever installing or modifying the physical $100\ \Omega$ parallel shunt resistor on the Kepco programming input.

---

## 1. System Architecture & The Hardware Difference

The Lake Shore 370 heater output is a **programmable DC current source** ($I$), whereas the Kepco power supply programming input expects an **analog voltage reference** ($V$).

```
[ Lake Shore 370 Output ]  --->  (I_out)  ---> [ Optional Parallel Shunt ] ---> [ Kepco BOP Program Input ]
    (Current Source)                                   (R_shunt)                      (Voltage Reference)
                                                           │
                                                          GND
                                            V_program = I_out × R_shunt
```

### KPAC Configuration (With $100\ \Omega$ Parallel Shunt)
* **Physical Circuit**: A **$100\ \Omega$ precision resistor** is connected in parallel across the Lake Shore output / Kepco programming input terminals.
* **Current-to-Voltage Conversion**: $V_\text{Kepco} = I_\text{LS370} \times 100\ \Omega$.
* **Ramp Settings**:
  * Output Range: **`10mA`** (`HTRRNG 6`)
  * Target Output: $\approx \mathbf{80\%}$ to reach full field ($14\text{ A}$)
  * Math: $0.80 \times 10\text{ mA} = 8.0\text{ mA} \implies 8.0\text{ mA} \times 100\ \Omega = \mathbf{0.80\text{ V}}$ programming input.
* **Regulation**: Operates with $R_\text{shunt} = 100\ \Omega$ defining the loop transfer function.

---

### 2PAC Current State (Without Parallel Shunt — As of 2026-10-15)
* **Physical Circuit**: The Lake Shore output connects directly into the Kepco programming terminals **without** a parallel shunt resistor.
* **Input Impedance**: The Kepco current-mode input behaves as an inverting op-amp summing junction (virtual ground) with an effective impedance of **$R_\text{in} \le 1\ \Omega$**.
* **The 100 Ω vs 1 Ω Software Mismatch**:
  * Previously, the software (`CSET`) was configured for `100.0 Ω` load resistance.
  * Because the physical load was actually $\le 1\ \Omega$, the Lake Shore's internal loop calculations (power scaling, compliance modeling, and gain) were off by $100\times$.
  * Changing the software setting to **`1.0 Ω`** on 2026-10-15 correctly matched the instrument model to the low-impedance input, immediately restoring control authority.
* **Why KPAC PID gains failed on 2PAC**:
  * Open loop gain: $K_\text{loop} \propto P \times R_\text{shunt} \times G_\text{Kepco}$.
  * With $R \approx 1\ \Omega$ instead of $100\ \Omega$, 2PAC had $\sim 100\times$ less voltage generated per mA of Lake Shore output. Copying KPAC's PID gains directly produced a massive loop gain deficit.

---

## 2. Checklist When Installing the 100 Ω Physical Shunt on 2PAC

When you physically insert the $100\ \Omega$ resistor in parallel across the Kepco programming input, **you must update the current ranges and software settings before energizing**:

### ⚠️ Critical Pre-Energize Warning
> [!CAUTION]
> **DO NOT** energize the Lake Shore on high current ranges (e.g. $100\text{ mA}$) with the $100\ \Omega$ resistor installed!
> By Ohm's law:
> $$V = I \times R = 100\text{ mA} \times 100\ \Omega = 10.0\text{ V}$$
> $10\text{ V}$ is the maximum compliance voltage of the Lake Shore 370 and would severely overdrive the Kepco power supply to its maximum output rail limit.

### Configuration Changes Required

| Setting | Before (No Shunt / $1\ \Omega$) | After Installing $100\ \Omega$ Shunt | Reason |
| :--- | :--- | :--- | :--- |
| **Physical Shunt** | None (direct into Kepco) | **$100\ \Omega$ in parallel** | Converts Lake Shore current to Kepco control voltage |
| **Ramp Current Range** | High current / direct range | **`10mA` range** (`HTRRNG 6`) | $8\text{ mA} \times 100\ \Omega = 0.8\text{ V}$ commands $\approx 14\text{ A}$ |
| **Full Field Output %** | Determined by $1\ \Omega$ scale | **$\approx 58\%\text{ to }80\%$** | Matches Kepco full field voltage target |
| **Software Load Resistor (`CSET`)** | `1.0 Ω` | **`100.0 Ω`** | Updates LS370 internal power & loop scaling to $100\ \Omega$ |
| **Current Limit Setting** | Adjusted for $1\ \Omega$ | **Limit Code 6 (`10mA`)** or matched | Prevents over-current fault |
| **PID Transfer from KPAC** | Did not work (gain deficit) | **Direct 1:1 transfer valid** | Loop transfer functions ($V/I$) are now identical |

---

## 3. Step-by-Step Transition Procedure

1. **Safety Interlock**: Ensure the system is in `wait_forever` (Idle), Lake Shore heater output is `0.0%`, heater range is `OFF`, and magnet current is confirmed zero ($|I| < 0.05\text{ A}$).
2. **Install Hardware**: Place the $100\ \Omega$ precision resistor in parallel across the Kepco remote programming input terminals.
3. **Update Software Settings in GUI**:
   - Go to the **Utilities** tab $\rightarrow$ **Temperature Control PID (LS370)**.
   - Set **Heater Resistance (R)**: `100.0 Ω`.
   - Set **Current Limit**: Code `6: 10 mA` (or code `7: 31.6 mA` depending on maximum safe threshold).
   - Set **Excitation Range**: `10mA` (for magnet ramping) or calibrated regulation range.
   - Enter the tested **KPAC PID gains** ($P, I, D$).
   - Click **Update and Apply Settings**.
4. **Update Recipe Defaults in Code**:
   - Verify `pid_config` in `gui_settings.json`:
     ```json
     "heater_resistance": 100.0,
     "heater_range": "10mA"
     ```
   - Verify `CSET` write in [`states.py`](file:///home/pcuser/qsp/src/2pac/states.py#L718):
     ```python
     ls.write(f"CSET {ch_val}, 1, 1, 1, 1, {limit_val}, 100.0")
     ```
5. **Verify with Low Setpoint First**: Test with a small setpoint step ($1\text{ to }2\text{ mK}$ or low magnet current) to confirm stable closed-loop response before running a full cycle.
