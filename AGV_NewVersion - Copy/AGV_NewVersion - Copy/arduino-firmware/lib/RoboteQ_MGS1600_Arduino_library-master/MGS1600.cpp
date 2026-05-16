#include "MGS1600.h"

//-- public methods --//

//<<constructor>>
MGS1600::MGS1600(int _powerControl, int _forkRight, int _forkLeft, int _analogOut, int _pwmOut,
	int _leftMarker, int _rightMarker, int _trackPresent)
{
	powerControl = _powerControl; forkRight = _forkRight;
	forkLeft = _forkLeft; analogOut = _analogOut; pwmOut = _pwmOut;
	leftMarker = _leftMarker; rightMarker = _rightMarker;
	trackPresent = _trackPresent;

	leftMarkerDetected = false; rightMarkerDetected = false;

	// configure pin I/O state
	pinMode(powerControl, OUTPUT); pinMode(forkRight, OUTPUT); pinMode(forkLeft, OUTPUT);
	pinMode(analogOut, INPUT); pinMode(pwmOut, INPUT); pinMode(leftMarker, INPUT);
	pinMode(rightMarker, INPUT); pinMode(trackPresent, INPUT);

	// initialize outputs
	digitalWrite(powerControl, HIGH);	// turn sensor on
	digitalWrite(forkRight, LOW); digitalWrite(forkLeft, HIGH);
}

//<<destructor>>
MGS1600::~MGS1600() {

}


unsigned int MGS1600::readAnalog()
{
	return analogRead(analogOut);
}

unsigned long MGS1600::readPulse()
{
	return pulseIn(pwmOut, HIGH, 5000);
}

bool MGS1600::trackDetected()
{
	return digitalRead(trackPresent);
}

void MGS1600::setForkLeft()
{
	digitalWrite(forkLeft, true);
	digitalWrite(forkRight, false);
}

void MGS1600::setForkRight()
{
	digitalWrite(forkLeft, false);
	digitalWrite(forkRight, true);
}

//-- private methods --//