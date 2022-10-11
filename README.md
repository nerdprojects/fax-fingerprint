# Fax Fingerprint
When a fax machine is called, it returns its device capabilities to the caller.
This script takes an audio recording of a fax transmission and parses these capability and prints them to the screen.
Therefore it is possible to fingerprint fax machines, by calling them, recording the audio and running it through this script.

## Usage
- Plug your mobile phone headphone jack into your computer
- Start audio recording (i use Audacity)
- Call a fax machine and record the audio
- Save the audio as a floating point WAV file
- Run the script on the WAV file to parse the T.30 HDLC frames in the fax transmission

Note that the script has no audio correction features. It needs to have a clean recording.
I think VoIP service and changes in volume can lead to recordings that are unparsable.
The software has surely some room for improvement.

There is also a recording from a fax transmission in the repository that I made at home.
It can be run through the script as an example.
