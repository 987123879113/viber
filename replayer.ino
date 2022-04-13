#include "replayer.h"
#include "state.h"

constexpr int CACHE_SIZE = 100;

int chartCursor;
int curChartEventStartIdx;
char curChartTitle[32];
unsigned int curChartEventCount;
unsigned int curChartEventIdx;

uint32_t curChartEventTimestamps[CACHE_SIZE];
uint8_t curChartEventNotes[CACHE_SIZE];

void replayerInit()
{
  chartCursor = 0;
  curChartEventCount = 0;
  curChartEventIdx = 0;
  curChartEventStartIdx = 0;
  memset(curChartTitle, 0, sizeof(char) * 32);
  memset(curChartEventTimestamps, 0, sizeof(uint32_t) * CACHE_SIZE);
  memset(curChartEventNotes, 0, sizeof(uint8_t) * CACHE_SIZE);

  resetInputs();
}

void resetInputs()
{
  arrowState[0] = arrowState[1] = arrowState[2] = arrowState[3] = false;

  Joystick.setButton(0, arrowState[0]);
  Joystick.setButton(1, arrowState[1]);
  Joystick.setButton(2, arrowState[2]);
  Joystick.setButton(3, arrowState[3]);
  Joystick.sendState();

  digitalWrite(JAMMA_LEFT, arrowState[0] ? LOW : HIGH);
  digitalWrite(JAMMA_DOWN, arrowState[1] ? LOW : HIGH);
  digitalWrite(JAMMA_UP, arrowState[2] ? LOW : HIGH);
  digitalWrite(JAMMA_RIGHT, arrowState[3] ? LOW : HIGH);
}

void loadChart()
{
  curChartEventStartIdx = pgm_read_dword(&charts[chartCursor].event_start_idx);
  curChartEventIdx = 0;

  int copyCount = curChartEventIdx + CACHE_SIZE > curChartEventCount ? curChartEventCount - curChartEventIdx : CACHE_SIZE;
  memcpy_P(curChartEventNotes, &event_notes[curChartEventStartIdx + curChartEventIdx], sizeof(uint8_t) * copyCount);
  memcpy_P(curChartEventTimestamps, &event_timestamps[curChartEventStartIdx + curChartEventIdx], sizeof(uint32_t) * copyCount);
}

void updateScreenChartReplay()
{
  u8g.firstPage();
  do
  {
    curChartEventCount = pgm_read_dword(&charts[chartCursor].event_count);
    memcpy_P(curChartTitle, &charts[chartCursor].title, 32);

    String chart_str = "Chart " + String(chartCursor + 1) + "/" + String(VIBERCHART_CHARTCOUNT);
    String title_str = String(curChartTitle);
    String events_str = "Events: " + String(curChartEventCount);

    u8g.drawStr(2, 8, chart_str.c_str());
    u8g.drawStr(2, 24, title_str.c_str());

    if (playbackState == PLAYBACK_STARTED) {
      u8g.drawStr(2, 40, "State: STARTED");
    }
    else if (playbackState == PLAYBACK_STOPPED) {
      u8g.drawStr(2, 40, "State: STOPPED");
    }
    else if (playbackState == PLAYBACK_PRIMED) {
      u8g.drawStr(2, 40, "State: PRIMED");
    }
    else {
      u8g.drawStr(2, 40, "State: UNKNOWN");
    }

    u8g.drawStr(2, 56, events_str.c_str());
  } while ( u8g.nextPage() );
}

void updateButtonStateChartReplay()
{
  bool updateButtons = false;

  if (playbackState == PLAYBACK_STOPPED) {
    if (buttonHeldState[2]) {
      if (buttonPressedDuration[2] > 500000UL) {
        // Start chart
        playbackState = PLAYBACK_PRIMED;
        updateButtons = true;
      }
    } else if (buttonIsPressedNow[1]) {
      chartCursor -= 1;
      if (chartCursor < 0)
        chartCursor = VIBERCHART_CHARTCOUNT - 1;
      loadChart();
    } else if (buttonIsPressedNow[0]) {
      chartCursor += 1;
      if (chartCursor >= VIBERCHART_CHARTCOUNT)
        chartCursor = 0;
      loadChart();
    }
  } else if (playbackState == PLAYBACK_PRIMED || playbackState == PLAYBACK_STARTED) {
    if (buttonIsPressedNow[2]) {
      // Stop
      playbackState = PLAYBACK_STOPPED;
      updateButtons = true;
    } else if (buttonIsPressed[0]) {
      if (!timeSyncPressed) {
        updateScreenChartReplay();
        updateButtons = true;
      }

      timeSyncPressed = true;
    } else if (timeSyncPressed && !buttonIsPressed[0]) {
      playbackState = PLAYBACK_STARTED;
      //updateScreenChartReplay(); // Slow
      updateButtons = true;
      loadChart();
      curChartEventIdx = 0;
      timeBeat = micros();
      timeSyncPressed = false;
    }
  }

  if (updateButtons) {
    resetInputs();
  }
}

void updateEventHandler()
{
  if (playbackState != PLAYBACK_STARTED || curChartEventIdx > curChartEventCount || timeSyncPressed) {
    return;
  }

  timeNow = micros();

  uint32_t curChartEventTimestamp = curChartEventTimestamps[curChartEventIdx % CACHE_SIZE];
  signed long diff = timeNow - timeBeat;
  signed long diff2 = diff - curChartEventTimestamp;
  if (abs(diff2) <= 16 || diff >= curChartEventTimestamp) { // Try to reduce the distance from the timestamp by accepting slightly earlier presses if they're within a certain range
    //Serial.println(diff2);

    uint8_t curChartEventNote = curChartEventNotes[curChartEventIdx % CACHE_SIZE];

    bool updateJoystick = false;
    if (curChartEventNote & 0x10) {
      bool state = (curChartEventNote & 1) != 0;
      if (state != arrowState[0]) {
        arrowState[0] = state;
        Joystick.setButton(0, arrowState[0]);

        digitalWrite(JAMMA_LEFT, arrowState[0] ? LOW : HIGH);
          
        updateJoystick = true;
      }
    }
    if (curChartEventNote & 0x20) {
      bool state = (curChartEventNote & 2) != 0;
      if (state != arrowState[1]) {
        arrowState[1] = state;
        Joystick.setButton(1, arrowState[1]);

        digitalWrite(JAMMA_DOWN, arrowState[1] ? LOW : HIGH);
          
        updateJoystick = true;
      }
    }
    if (curChartEventNote & 0x40) {
      bool state = (curChartEventNote & 4) != 0;
      if (state != arrowState[2]) {
        arrowState[2] = state;
        Joystick.setButton(2, arrowState[2]);
        
        digitalWrite(JAMMA_UP, arrowState[2] ? LOW : HIGH);
          
        updateJoystick = true;
      }
    }
    if (curChartEventNote & 0x80) {
      bool state = (curChartEventNote & 8) != 0;
      if (state != arrowState[3]) {
        arrowState[3] = state;
        Joystick.setButton(3, arrowState[3]);

        digitalWrite(JAMMA_RIGHT, arrowState[3] ? LOW : HIGH);
          
        updateJoystick = true;
      }
    }

    if (updateJoystick)
      Joystick.sendState();

    curChartEventIdx++;

    if (curChartEventIdx > curChartEventCount) {
      playbackState = PLAYBACK_STOPPED;
    } else if ((curChartEventIdx % CACHE_SIZE) == 0) {
      int copyCount = curChartEventIdx + CACHE_SIZE > curChartEventCount ? curChartEventCount - curChartEventIdx : CACHE_SIZE;
      memcpy_P(curChartEventNotes, &event_notes[curChartEventStartIdx + curChartEventIdx], sizeof(uint8_t) * copyCount);
      memcpy_P(curChartEventTimestamps, &event_timestamps[curChartEventStartIdx + curChartEventIdx], sizeof(uint32_t) * copyCount);
    }
  }
}
