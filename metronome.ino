#include "metronome.h"
#include "state.h"

const double DEFAULT_BPM = 120.0;

double curBpm;
unsigned long curBpmInMicros;
int beatsSent;

bool joypadState;

void metronomeInit()
{
  beatsSent = 0;
  timeNow = timeBeat = micros();
  timeSyncPressed = false;
  curBpm = DEFAULT_BPM;
  joypadState = false;  
}


void setBpm(double bpm)
{
  curBpm = bpm;
  curBpmInMicros = (unsigned long)(MICROS_PER_MIN / bpm);
  Serial.print("curBpm: ");
  Serial.println(curBpm);
  Serial.print("curBpmInMicros: ");
  Serial.println(curBpmInMicros);
}

void updateScreenMetronome()
{
  u8g.firstPage();
  do
  {
    String bpm_str = "BPM: " + String(curBpm);
    u8g.drawStr(2, 8, bpm_str.c_str());

    if (buttonHeldState[2] && buttonPressedDuration[2] > 1000000UL) {
      u8g.drawStr(2, 24, "State: COMMAND");
    }
    else if (playbackState == PLAYBACK_STARTED) {
      u8g.drawStr(2, 24, "State: STARTED");
    }
    else if (playbackState == PLAYBACK_STOPPED) {
      u8g.drawStr(2, 24, "State: STOPPED");
    }
    else if (playbackState == PLAYBACK_PRIMED) {
      u8g.drawStr(2, 24, "State: PRIMED");
    }
    else {
      u8g.drawStr(2, 24, "State: UNKNOWN");
    }

    if (beatsSent != 0) {
      String beats_str = "Beats: " + String(beatsSent);
      u8g.drawStr(2, 40, beats_str.c_str());
    }
  } while ( u8g.nextPage() );
}

void updateButtonStateMetronome()
{
  if (playbackState == PLAYBACK_STARTED) {
    if (buttonIsPressedNow[2]) {
      playbackState = PLAYBACK_STOPPED;
    }
    else if (buttonIsPressedNow[0]) {
      timeSyncPressed = true;
    }
    else if (!buttonIsPressedNow[0]) {
      if (timeSyncPressed) {
        timeBeat = micros() - curBpmInMicros;
      }

      timeSyncPressed = false;
    }
  } else if (playbackState == PLAYBACK_PRIMED) {
    if (buttonIsPressedNow[1]) {
      playbackState = PLAYBACK_STARTED;
      resetAllButtonStates();
      updateScreenMetronome();
      beatsSent = 0;
      timeBeat = micros() - curBpmInMicros;
    }
  } else if (buttonHeldState[2]) {
    if (buttonPressedDuration[2] > 1000000UL) {
      updateScreenMetronome();

      if (buttonIsPressedNow[0] && !buttonIsPressedNow[1]) {
        playbackState = playbackState != PLAYBACK_STOPPED ? PLAYBACK_STOPPED : PLAYBACK_PRIMED;
        resetAllButtonStates();
        setBpm(curBpm);
      } else if (!buttonIsPressedNow[0] && buttonIsPressedNow[1]) {
        // Only clear BPM if button has been held
        setBpm(DEFAULT_BPM);
        resetAllButtonStates();
      }
    } else if (buttonHeldState[0] && !buttonHeldState[1]) {
      setBpm(curBpm + 2.50);
      resetAllButtonStates();
    } else if (!buttonHeldState[0] && buttonHeldState[1]) {
      setBpm(curBpm - 2.50);
      resetAllButtonStates();
    }
  } else if (buttonHeldState[0] && !buttonHeldState[1] && !buttonHeldState[2]) {
    setBpm(curBpm + 0.25);
    resetAllButtonStates();
  } else if (!buttonHeldState[0] && buttonHeldState[1] && !buttonHeldState[2]) {
    setBpm(curBpm - 0.25);
    resetAllButtonStates();
  }
}

void updateMetronome()
{
  if (playbackState != PLAYBACK_STARTED)
    return;
    
  timeNow = micros();

  unsigned long diff = timeNow - timeBeat;

  if (timeSyncPressed) {
    timeBeat += diff;
    return;
  }

  signed long diff2 = diff - curBpmInMicros;
  if (abs(diff2) <= 8 || diff >= curBpmInMicros) {
    //Serial.println(diff2);

    beatsSent++;
    timeBeat = timeNow + diff2; // Adjust for some variance

    if (joypadState == false) {
      joypadState = true;
      Joystick.setButton(0, joypadState);
      digitalWrite(JAMMA_UP, joypadState);
      digitalWrite(JAMMA_DOWN, joypadState);
      digitalWrite(JAMMA_LEFT, joypadState);
      digitalWrite(JAMMA_RIGHT, joypadState);
      Joystick.sendState();
    }
  } else {
    if (joypadState == true && diff > 25000) {
      joypadState = false;
      Joystick.setButton(0, joypadState);
      digitalWrite(JAMMA_UP, joypadState);
      digitalWrite(JAMMA_DOWN, joypadState);
      digitalWrite(JAMMA_LEFT, joypadState);
      digitalWrite(JAMMA_RIGHT, joypadState);
      Joystick.sendState();
    }
  }
}
