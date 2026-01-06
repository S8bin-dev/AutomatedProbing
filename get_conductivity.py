#!/usr/bin/env python3
"""
Automated Four-Point Probe Measurement System
Combines Thorlabs stage positioning with xtralien four-point probe.
Now includes Electrical Conductivity extraction.
"""

import xtralien
import time
import csv
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from pylablib.devices import Thorlabs

# ================= CONFIGURATION =================
# Device Ports
STAGE_PORT = '/dev/ttyUSB0'
PROBE_PORT = '/dev/ttyACM0'

# Stage Settings
CONTACT_HEIGHT_MM = 5.4      # Height where probe contacts sample
STEPS_PER_MM = 34304
CONTACT_HEIGHT_STEPS = int(CONTACT_HEIGHT_MM * STEPS_PER_MM)
SETTLING_TIME = 1.0          # Seconds to wait after reaching height

# Contact Verification
TEST_VOLTAGE = 0.1           # V - small voltage to verify contact
CONTACT_THRESHOLD = 0.0001   # A (0.1 mA) - minimum current for good contact
RETRY_INCREMENT_MM = 0.1     # mm - how much to raise stage if no contact

# FTO/Polymer Measurement Settings
START_V = -0.5
END_V = 0.5
STEP_V = 0.02
CURRENT_LIMIT = 0.2          # 200mA max

# Geometry & Calculation
CORRECTION_FACTOR = 4.532    # For 6cm x 6cm sample (Sheet Resistance)

# Output
RESULTS_FOLDER = "results_automated"
# =================================================


class AutomatedProbeSystem:
    def __init__(self):
        self.stage = None
        self.probe = None
        self.sample_name = None
        self.thickness_m = None # Thickness in meters
        
    def connect_devices(self):
        """Connect to both stage and probe."""
        print("\n" + "="*60)
        print("  CONNECTING TO DEVICES")
        print("="*60)
        
        # Connect stage
        try:
            print(f"Connecting to Thorlabs stage ({STAGE_PORT})...")
            self.stage = Thorlabs.KinesisMotor(STAGE_PORT, is_rack_system=False)
            self.stage._enable_channel()
            time.sleep(0.3)
            
            if not self.stage.is_homed():
                print("ERROR: Stage is not homed!")
                print("Please run 'check_connection.py' first.")
                return False
                
            print("✓ Stage connected and homed")
            
        except Exception as e:
            print(f"✗ Stage connection failed: {e}")
            return False
        
        # Connect probe
        try:
            print(f"Connecting to four-point probe ({PROBE_PORT})...")
            self.probe = xtralien.Device(PROBE_PORT)
            print("✓ Probe connected")
            
        except Exception as e:
            print(f"✗ Probe connection failed: {e}")
            if self.stage:
                self.stage.close()
            return False
        
        print("\n✓ All devices connected successfully!")
        return True
    
    def get_sample_details(self):
        """Prompt user for sample name and thickness."""
        print("\n" + "="*60)
        print("  SAMPLE IDENTIFICATION & GEOMETRY")
        print("="*60)
        
        # 1. Sample Name
        name = input("Enter sample name (or press Enter for default): ").strip()
        if name:
            # Sanitize filename
            name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
            self.sample_name = name
        else:
            self.sample_name = "FTO"
        
        # 2. Sample Thickness
        while True:
            t_input = input("Enter film thickness in mm (e.g., 0.001): ").strip()
            try:
                thickness_mm = float(t_input)
                if thickness_mm <= 0:
                    print("Thickness must be positive.")
                    continue
                # Convert mm to meters for SI calculation
                self.thickness_m = thickness_mm * 1e-3
                print(f"✓ Thickness set: {thickness_mm} mm ({self.thickness_m:.2e} m)")
                break
            except ValueError:
                print("Invalid input. Please enter a number.")

        print(f"Sample: {self.sample_name}")
    
    def move_to_contact(self):
        """Move stage to contact height."""
        print("\n" + "="*60)
        print("  MOVING TO CONTACT POSITION")
        print("="*60)
        
        current_pos = self.stage.get_position()
        current_mm = current_pos / STEPS_PER_MM
        
        print(f"Current position: {current_mm:.2f} mm")
        print(f"Target position: {CONTACT_HEIGHT_MM:.2f} mm")
        print("Moving...")
        
        self.stage.move_to(CONTACT_HEIGHT_STEPS)
        self.stage.wait_move()
        
        final_pos = self.stage.get_position()
        final_mm = final_pos / STEPS_PER_MM
        print(f"✓ Reached: {final_mm:.2f} mm")
        
        print(f"Settling for {SETTLING_TIME}s...")
        time.sleep(SETTLING_TIME)
        
        return final_mm
    
    def verify_contact(self, current_height_mm):
        """Verify probe is making contact with sample."""
        print("\n" + "="*60)
        print("  VERIFYING CONTACT")
        print("="*60)
        
        # Configure probe for test
        self.probe.smu1.set.limiti(CURRENT_LIMIT, response=0)
        self.probe.smu1.set.limitv(10.0, response=0)
        self.probe.smu1.set.enabled(True, response=0)
        
        # Apply test voltage
        print(f"Applying test voltage: {TEST_VOLTAGE}V")
        data = self.probe.smu1.oneshot(TEST_VOLTAGE)
        
        meas_v = float(data[0][0])
        meas_i = abs(float(data[0][1]))
        
        print(f"Measured: V = {meas_v:.4f}V, I = {meas_i*1000:.4f}mA")
        print(f"Threshold: {CONTACT_THRESHOLD*1000:.4f}mA")
        
        # Reset to 0V
        self.probe.smu1.set.voltage(0, response=0)
        
        if meas_i >= CONTACT_THRESHOLD:
            print("✓ GOOD CONTACT DETECTED!")
            return True
        else:
            print("⚠ WARNING: Low or no current detected")
            print("The probe may not be making good contact with the sample.")
            print(f"\nCurrent height: {current_height_mm:.2f} mm")
            print("\nOptions:")
            print("  1. Retry at higher position (+0.1mm)")
            print("  2. Abort and check sample placement")
            print("  3. Override and measure anyway")
            
            while True:
                choice = input("\nEnter choice (1/2/3): ").strip()
                
                if choice == '1':
                    # Retry at higher position
                    new_height_mm = current_height_mm + RETRY_INCREMENT_MM
                    new_height_steps = int(new_height_mm * STEPS_PER_MM)
                    
                    print(f"\nMoving to {new_height_mm:.2f} mm...")
                    self.stage.move_to(new_height_steps)
                    self.stage.wait_move()
                    time.sleep(SETTLING_TIME)
                    
                    return self.verify_contact(new_height_mm)
                
                elif choice == '2':
                    print("\nAborting measurement.")
                    return False
                
                elif choice == '3':
                    print("\nOverriding contact check - proceeding with measurement...")
                    return True
                
                else:
                    print("Invalid choice. Please enter 1, 2, or 3.")
    
    def run_measurement(self):
        """Perform the four-point probe measurement and calculate conductivity."""
        print("\n" + "="*60)
        print("  RUNNING MEASUREMENT")
        print("="*60)
        
        # Setup (already enabled from contact verification)
        voltages = np.arange(START_V, END_V + STEP_V/1000, STEP_V)
        results = []
        
        print(f"\nVoltage sweep: {START_V}V to {END_V}V (step: {STEP_V}V)")
        print(f"Assuming thickness: {self.thickness_m:.2e} m")
        print("-" * 80)
        print(f"{'Set V':>8} | {'Meas V':>8} | {'Current (mA)':>12} | {'Rs (Ω/sq)':>10} | {'Cond (S/m)':>12}")
        print("-" * 80)
        
        for set_v in voltages:
            try:
                # Measure
                data = self.probe.smu1.oneshot(float(set_v))
                
                # Extract
                meas_v = float(data[0][0])
                meas_i = float(data[0][1])
                
                # Calculate sheet resistance (Rs)
                if abs(meas_i) > 1e-7:
                    rs = (meas_v / meas_i) * CORRECTION_FACTOR
                else:
                    rs = 0
                
                # Calculate Conductivity (sigma = 1 / (Rs * t))
                # Avoid division by zero
                if abs(rs) > 1e-9 and self.thickness_m > 0:
                    sigma = 1 / (abs(rs) * self.thickness_m)
                else:
                    sigma = 0

                results.append([meas_i, meas_v, abs(rs), sigma])
                print(f"{set_v:>8.3f} | {meas_v:>8.3f} | {meas_i*1000:>12.3f} | {abs(rs):>10.2f} | {sigma:>12.2e}")
                
            except Exception as e:
                print(f"Error at {set_v}V: {e}")
        
        print("\n✓ Measurement complete!")
        return results
    
    def save_results(self, data):
        """Save measurement data to CSV and plot."""
        print("\n" + "="*60)
        print("  SAVING RESULTS")
        print("="*60)
        
        # Create results folder
        if not os.path.exists(RESULTS_FOLDER):
            os.makedirs(RESULTS_FOLDER)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{RESULTS_FOLDER}/{self.sample_name}_{timestamp}"
        
        # Save CSV
        with open(f"{filename}.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            # Added Conductivity column
            writer.writerow(["Current (A)", "Voltage (V)", "Sheet Resistance (Ohm/sq)", "Conductivity (S/m)"])
            writer.writerows(data)
        print(f"✓ Saved data: {filename}.csv")
        
        # Calculate averages (filter outliers for Rs > 5 Ohm)
        valid_rs = [r[2] for r in data if 5 < r[2] < 1000]
        avg_rs = np.mean(valid_rs) if valid_rs else 0
        
        # Calculate average conductivity
        valid_sigma = [r[3] for r in data if r[3] > 0 and 5 < r[2] < 1000]
        avg_sigma = np.mean(valid_sigma) if valid_sigma else 0
        
        # Save plot
        currents = [row[0] for row in data]
        voltages = [row[1] for row in data]
        
        plt.figure(figsize=(10, 6))
        plt.plot(voltages, currents, 'b-o', markersize=3)
        plt.title(f"IV Curve - {self.sample_name}\nAvg Rs: {avg_rs:.2f} Ω/sq | Avg $\sigma$: {avg_sigma:.2e} S/m")
        plt.xlabel("Voltage (V)")
        plt.ylabel("Current (A)")
        plt.grid(True)
        plt.savefig(f"{filename}.png", dpi=150)
        print(f"✓ Saved plot: {filename}.png")
        
        print("-" * 40)
        print(f"RESULTS SUMMARY")
        print("-" * 40)
        print(f"Average Sheet Resistance: {avg_rs:.4f} Ω/sq")
        print(f"Average Conductivity:     {avg_sigma:.4e} S/m")
        print("-" * 40)
    
    def return_home(self):
        """Return stage to home position."""
        print("\n" + "="*60)
        print("  RETURNING TO HOME")
        print("="*60)
        
        print("Moving stage to home position...")
        self.stage.move_to(0)
        self.stage.wait_move()
        
        final_pos = self.stage.get_position()
        print(f"✓ At home: {final_pos} steps")
    
    def shutdown(self):
        """Safely shutdown all devices."""
        print("\n" + "="*60)
        print("  SHUTTING DOWN")
        print("="*60)
        
        if self.probe:
            try:
                self.probe.smu1.set.voltage(0, response=0)
                self.probe.smu1.set.enabled(False, response=0)
                self.probe.close()
                print("✓ Probe shutdown complete")
            except:
                pass
        
        if self.stage:
            try:
                self.stage.close()
                print("✓ Stage shutdown complete")
            except:
                pass
    
    def run(self):
        """Main execution sequence."""
        try:
            # 1. Get sample details (Name & Thickness)
            self.get_sample_details()
            
            # 2. Connect devices
            if not self.connect_devices():
                return 1
            
            # 3. Move to contact height
            current_height = self.move_to_contact()
            
            # 4. Verify contact
            if not self.verify_contact(current_height):
                print("\nMeasurement aborted by user.")
                self.return_home()
                self.shutdown()
                return 1
            
            # 5. Run measurement
            data = self.run_measurement()
            
            # 6. Save results
            self.save_results(data)
            
            # 7. Return home
            self.return_home()
            
            # 8. Shutdown
            self.shutdown()
            
            print("\n" + "="*60)
            print("  ✓ MEASUREMENT COMPLETE!")
            print("="*60)
            return 0
            
        except KeyboardInterrupt:
            print("\n\nInterrupted by user!")
            self.shutdown()
            return 1
            
        except Exception as e:
            print(f"\n\nERROR: {e}")
            import traceback
            traceback.print_exc()
            self.shutdown()
            return 1


def main():
    print("\n" + "="*60)
    print("  AUTOMATED FOUR-POINT PROBE MEASUREMENT SYSTEM")
    print("="*60)
    print("\nConfiguration:")
    print(f"  Contact Height: {CONTACT_HEIGHT_MM} mm")
    print(f"  Voltage Range: {START_V}V to {END_V}V")
    print(f"  Step Size: {STEP_V}V")
    print(f"  Current Limit: {CURRENT_LIMIT}A")
    print(f"  Correction Factor: {CORRECTION_FACTOR}")
    
    print("\nEnsure:")
    print("  ✓ Sample is placed on stage (at home position)")
    print("  ✓ Probe is positioned above sample")
    print("  ✓ All connections are secure")
    
    input("\nPress Enter to begin measurement...")
    
    system = AutomatedProbeSystem()
    return system.run()


if __name__ == "__main__":
    sys.exit(main())