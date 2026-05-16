#ifndef MGS1600_H
#define MGS1600_H

#include <Arduino.h>

//class for reading and reporting data from the Roboteq MGS1600 magnetic guide sensor
class MGS1600 {
	public:
		MGS1600(int _powerControl, int _forkRight, int _forkLeft, int _analogOut, int _pwmOut,
			int _leftMarker, int _rightMarker, int _trackPresent);
		~MGS1600();
		unsigned int readAnalog();
		unsigned long readPulse();
		bool trackDetected();
		void setForkLeft();
		void setForkRight();

		//marker detected flags
		volatile bool leftMarkerDetected, rightMarkerDetected;

		//marker pins
		int leftMarker;
		int rightMarker;
	private:
		// pins
		int powerControl;
		int forkRight;
		int forkLeft;
		int analogOut;
		int pwmOut;
		
		int trackPresent;
};
#endif