#!/usr/bin/env python3
"""
Combined Device Connection Checker
Verifies both Thorlabs stage and xtralien four-point probe are ready.
Homes the stage if needed.
"""

import sys
import time

# Device ports
STAGE_PORT = "/dev/ttyUSB0"
PROBE_PORT = "/dev/ttyACM0"

def check_stage():
    """Check Thorlabs stage connection and home if needed."""
    print("\n" + "="*50)
    print("  CHECKING THORLABS STAGE")
    print("="*50)
    
    try:
        from pylablib.devices import Thorlabs
        
        print(f"Connecting to {STAGE_PORT}...")
        stage = Thorlabs.KinesisMotor(STAGE_PORT, is_rack_system=False)
        print("✓ Stage connected successfully!")
        
        # Enable the stage
        stage._enable_channel()
        time.sleep(0.3)
        
        # Check current status
        current_pos = stage.get_position()
        is_homed = stage.is_homed()
        
        print(f"Current Position: {current_pos} steps")
        print(f"Is Homed: {is_homed}")
        
        # Home if needed
        if not is_homed:
            print("\n⚠ Stage is NOT homed. Starting homing sequence...")
            print("(Watch for physical movement - this may take up to 2 minutes)")
            
            stage.home(sync=False)
            time.sleep(1)
            
            status = stage.get_status()
            print(f"Homing status: {status}")
            
            stage.wait_for_home(timeout=120)
            print("✓ Homing complete!")
            
            final_pos = stage.get_position()
            print(f"Final Position: {final_pos} steps (should be near 0)")
        else:
            print("✓ Stage is already homed.")
            
            # Move to home position if not there
            if abs(current_pos) > 10:
                print("Moving to home position (0)...")
                stage.move_to(0)
                stage.wait_move()
                print(f"✓ At home position: {stage.get_position()} steps")
            else:
                print("✓ Already at home position.")
        
        stage.close()
        print("\n✓ STAGE CHECK PASSED - Ready for measurements!")
        return True
        
    except ImportError:
        print("\n✗ ERROR: pylablib not installed")
        print("Install with: pip install pylablib")
        return False
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        print("\nTROUBLESHOOTING:")
        print("1. Check USB connection to stage")
        print("2. Run: sudo chmod 666 /dev/ttyUSB0")
        print("3. Unplug and replug USB if device is busy")
        return False


def check_probe():
    """Check xtralien four-point probe connection."""
    print("\n" + "="*50)
    print("  CHECKING FOUR-POINT PROBE")
    print("="*50)
    
    try:
        import xtralien
        
        print(f"Connecting to {PROBE_PORT}...")
        device = xtralien.Device(PROBE_PORT)
        print("✓ Probe connected successfully!")
        
        # Test basic communication
        response = device.cloi.hello()
        print(f"Device response: {response}")
        
        # Check temperature sensor
        temp = device.temp.read()
        print(f"Board Temperature: {temp}°C")
        
        device.close()
        print("\n✓ PROBE CHECK PASSED - Ready for measurements!")
        return True
        
    except ImportError:
        print("\n✗ ERROR: xtralien library not installed")
        print("Install with: pip install xtralien")
        return False
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        print("\nTROUBLESHOOTING:")
        print("1. Check USB connection to probe")
        print("2. Ensure no other script is using the device")
        print("3. Try unplugging and replugging the USB cable")
        return False


def main():
    print("\n" + "="*60)
    print("  AUTOMATED FOUR-POINT PROBE SYSTEM")
    print("  Connection Verification & Homing")
    print("="*60)
    
    # Check both devices
    stage_ok = check_stage()
    probe_ok = check_probe()
    
    # Final summary
    print("\n" + "="*60)
    print("  FINAL STATUS")
    print("="*60)
    print(f"Thorlabs Stage:     {'✓ READY' if stage_ok else '✗ FAILED'}")
    print(f"Four-Point Probe:   {'✓ READY' if probe_ok else '✗ FAILED'}")
    print("="*60)
    
    if stage_ok and probe_ok:
        print("\n✓ ALL SYSTEMS READY!")
        print("\nNext steps:")
        print("1. Place your sample on the stage (at home position)")
        print("2. Run: python3 automated_measurement.py")
        return 0
    else:
        print("\n✗ SYSTEM NOT READY")
        print("Fix the errors above before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())