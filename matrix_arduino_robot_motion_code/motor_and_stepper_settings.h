// Every number the MATRIX motion sketch needs, in one place.
//
// ============================================================================
// READ THIS BEFORE FLASHING
// ============================================================================
// Values marked MUST BE CONFIRMED are placeholders. They are NOT measurements
// and they are NOT copied from working code, because the previous repository
// had none for this robot: its firmware was written for the older gantry
// machine with an X and Y sensor carriage, and it was already marked
// deprecated before the mecanum chassis existed.
//
// A wrong steps-per-revolution or a wrong wheel diameter does not crash. It
// makes the robot quietly travel the wrong distance, which is much harder to
// notice. Measure each one on the actual robot, write it in here, and record
// what you measured in notes_for_matrix_motor_wiring_and_commands.md.
// ============================================================================

#ifndef MOTOR_AND_STEPPER_SETTINGS_H
#define MOTOR_AND_STEPPER_SETTINGS_H

// ---------------------------------------------------------------------------
// Serial link up to the main ESP32
// ---------------------------------------------------------------------------

// MUST BE CONFIRMED. Whatever you choose here has to match
// MATRIX_SERIAL_BAUD_RATE in the main ESP32 sketch and the value in
// settings.json. 115200 is a sensible starting point, but confirm the link
// actually runs cleanly at it before writing it down as final.
#define MATRIX_SERIAL_BAUD_RATE 115200

// How long the Arduino waits for a command line before going back round the
// loop. Short, because the loop also has to keep the motors updated.
#define SERIAL_READ_TIMEOUT_MS 20


// ---------------------------------------------------------------------------
// The four mecanum wheel motors
// ---------------------------------------------------------------------------
// The MATRIX controller drives its motors through the MATRIX library rather
// than through raw Arduino pins, so what belongs here is the PORT each motor
// is plugged into, not a GPIO number.
//
// MUST BE CONFIRMED: look at the robot and write down which motor is in which
// MATRIX motor port.

#define MOTOR_PORT_FRONT_LEFT   1
#define MOTOR_PORT_FRONT_RIGHT  2
#define MOTOR_PORT_REAR_LEFT    3
#define MOTOR_PORT_REAR_RIGHT   4

// Some motors are mounted facing the other way, so a positive command makes
// them turn backwards. Set the ones that need it to -1 once you have driven
// the robot and seen which wheels go the wrong way.
// MUST BE CONFIRMED by driving the robot.
#define MOTOR_DIRECTION_FRONT_LEFT   1
#define MOTOR_DIRECTION_FRONT_RIGHT  1
#define MOTOR_DIRECTION_REAR_LEFT    1
#define MOTOR_DIRECTION_REAR_RIGHT   1

// Motor power used when travelling between scan areas, as a percentage.
// Slow is good here: the robot has to stop accurately and stop vibrating
// quickly, and it is not racing anyone.
#define TRAVEL_MOTOR_POWER_PERCENT 35
#define TURN_MOTOR_POWER_PERCENT   30


// ---------------------------------------------------------------------------
// Encoders
// ---------------------------------------------------------------------------
// MUST BE CONFIRMED. Counts per full turn of the WHEEL, after the gearbox.
// Measure it: lift the robot, mark a wheel, turn it exactly ten times by hand
// while printing the encoder count, then divide by ten.
#define ENCODER_COUNTS_PER_WHEEL_TURN 0

// MUST BE CONFIRMED. Measure the wheel across its widest point, in
// millimetres, with the robot standing on it so the rollers are compressed the
// way they will be when driving.
#define WHEEL_DIAMETER_MM 0.0f

// How far the robot moves between two scan areas, in millimetres.
// MUST BE CONFIRMED once the scanning window and the camera field of view are
// both known. It has to be small enough that two neighbouring areas do not
// overlap and large enough that they are genuinely different parts of the
// cloth.
#define DISTANCE_BETWEEN_SCAN_AREAS_MM 0.0f

// How close to the target distance counts as arrived, in encoder counts.
#define ENCODER_ARRIVAL_TOLERANCE_COUNTS 5

// Give up on a move that takes longer than this and report ERROR, rather than
// leaving the main ESP32 waiting for a DONE that is never coming.
#define MOVE_TIMEOUT_MS 8000

// Time to let the chassis stop shaking after the wheels stop, before the
// camera is allowed to take a photo.
#define SETTLE_AFTER_STOPPING_MS 400


// ---------------------------------------------------------------------------
// NEMA 17 pancake stepper, driven through the HW-134A module
// ---------------------------------------------------------------------------
// The HW-134A takes step, direction and enable, which is the ordinary way of
// driving a stepper: one pulse on the step pin moves the motor one step, and
// the direction pin decides which way.
//
// MUST BE CONFIRMED: which Arduino pins these three wires are actually in.

#define STEPPER_STEP_PIN   0
#define STEPPER_DIR_PIN    0
#define STEPPER_ENABLE_PIN 0

// Most HW-134A boards disable the motor when the enable pin is HIGH. Check
// yours: if the motor is stiff when it should be free, flip this.
// MUST BE CONFIRMED.
#define STEPPER_ENABLE_IS_ACTIVE_LOW 1

// A 1.8 degree NEMA 17 takes 200 full steps per turn. The HW-134A then
// multiplies that by its microstepping setting, which is chosen with the small
// switches on the module.
// MUST BE CONFIRMED: read the switch positions on your module and multiply.
#define STEPPER_FULL_STEPS_PER_TURN 200
#define STEPPER_MICROSTEPS 1
#define STEPPER_STEPS_PER_TURN (STEPPER_FULL_STEPS_PER_TURN * STEPPER_MICROSTEPS)

// How long the step pin is held high for one pulse, and how long between
// pulses. Longer between pulses means a slower but stronger movement. Start
// slow: a stepper that is asked to go too fast silently skips steps, and then
// the scanning axis is in the wrong place with nothing reporting a fault.
#define STEPPER_PULSE_WIDTH_US 5
#define STEPPER_STEP_INTERVAL_US 1200

// The furthest the scanning axis is allowed to travel from its parked
// position, so a bad command cannot drive the mechanism into its end stop.
// MUST BE CONFIRMED by moving the axis by hand and counting.
#define STEPPER_MAXIMUM_STEPS_FROM_PARKED 0


// ---------------------------------------------------------------------------
// MATRIX colour sensor
// ---------------------------------------------------------------------------
// The colour sensor stays on the MATRIX controller. That is where it was in
// the previous repository and where it is wired on the robot, and moving a
// sensor from one board to another because a diagram looks tidier is exactly
// the kind of change that quietly invalidates every calibration.
//
// MUST BE CONFIRMED: which MATRIX sensor port it is plugged into.
#define COLOUR_SENSOR_PORT 1

// How many readings to average for one scan. Averaging a few readings takes
// almost no time and removes most of the flicker.
#define COLOUR_SENSOR_READINGS_TO_AVERAGE 5

// The sensor reports red, green and blue in this order, and the laptop expects
// them in this order. Changing the order here without changing it on the
// laptop would feed the classifier red as if it were blue.
#define COLOUR_SENSOR_CHANNEL_COUNT 3

#endif  // MOTOR_AND_STEPPER_SETTINGS_H
