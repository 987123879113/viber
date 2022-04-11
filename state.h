#ifndef __STATE_H__
#define __STATE_H__

enum PlaybackState {
  PLAYBACK_STOPPED = 0,
  PLAYBACK_STARTED,
  PLAYBACK_PRIMED
};

extern bool buttonIsPressed[3];
extern bool buttonIsPressedNow[3];
extern bool buttonHeldState[3];
extern unsigned long buttonHeldStartTime[3];
extern unsigned long buttonPressedDuration[3];
extern PlaybackState playbackState;

extern unsigned long timeNow, timeBeat;
extern bool timeSyncPressed;

extern bool arrowState[4];

#endif
