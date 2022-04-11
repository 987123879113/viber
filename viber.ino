#include <Joystick.h>
#include <U8glib.h>

#define INCLUDE_METRONOME
#define INCLUDE_REPLAYER

const double MICROS_PER_MIN = 60000000.0;

const int PIN_BUTTON1 = 15;
const int PIN_BUTTON2 = 16;
const int PIN_BUTTON3 = 14;

const int JAMMA_UP = A3;
const int JAMMA_DOWN = A2;
const int JAMMA_LEFT = A1;
const int JAMMA_RIGHT = A0;

#include "viberchart.h"
#include "state.h"

#ifdef INCLUDE_METRONOME
#include "metronome.h"
#endif

#ifdef INCLUDE_REPLAYER
#include "replayer.h"
#endif

#ifdef INCLUDE_METRONOME && INCLUDE_REPLAYER
bool isMetronomeMode;
int metronomeCheckIdx;
unsigned long metronomeChecks[3];

const unsigned long MODE_SWITCH_DELAY_US = 750000UL;
#endif

const int pinButtons[] = {PIN_BUTTON1, PIN_BUTTON2, PIN_BUTTON3};
const int jammaButtons[] = {JAMMA_UP, JAMMA_DOWN, JAMMA_LEFT, JAMMA_RIGHT};

bool buttonIsPressed[3];
bool buttonIsPressedNow[3];
bool buttonHeldState[3];
unsigned long buttonHeldStartTime[3];
unsigned long buttonPressedDuration[3];
PlaybackState playbackState;

unsigned long timeNow, timeBeat;
bool timeSyncPressed;

bool arrowState[4];

U8GLIB_SSD1306_128X64 u8g(U8G_I2C_OPT_NO_ACK);

Joystick_ Joystick(JOYSTICK_DEFAULT_REPORT_ID, JOYSTICK_TYPE_GAMEPAD,
                   4, 1,                  // Button Count, Hat Switch Count
                   false, false, false,   // X, Y and Z Axis
                   false, false, false,   // No Rx, Ry, or Rz
                   false, false,          // No rudder or throttle
                   false, false, false);  // No accelerator, brake, or steering

uint8_t buttonPinMask[3];
volatile uint8_t *buttonPinPort[3];
    
void setup(void)
{
  timeNow = micros();
  playbackState = PLAYBACK_STOPPED;

  for (int i = 0; i < 3; i++) {
    pinMode(pinButtons[i], INPUT);
    buttonPinMask[i] = digitalPinToBitMask(pinButtons[i]);
    buttonPinPort[i] = portInputRegister(digitalPinToPort(pinButtons[i]));
    resetButton(i);
  }

  // Initialize OLED
  u8g.setFont(u8g_font_6x10);
  u8g.setFontRefHeightExtendedText();
  u8g.setDefaultForegroundColor();
  u8g.setFontPosTop();
  u8g.setRot180();

  // Initialize joystick and JAMMA I/O
  arrowState[0] = arrowState[1] = arrowState[2] = arrowState[3] = false;
  Joystick.begin(false);

  for (int i = 0; i < 4; i++) {
    pinMode(jammaButtons[i], OUTPUT);
    digitalWrite(jammaButtons[i], HIGH);
    
    Joystick.setButton(i, arrowState[i]);
  }

#ifdef INCLUDE_METRONOME
  metronomeInit();
#endif

#ifdef INCLUDE_REPLAYER
  replayerInit();
#endif

#if defined(INCLUDE_METRONOME) && defined(INCLUDE_REPLAYER)
  isMetronomeMode = false;
  metronomeCheckIdx = 0;
  metronomeChecks[0] = metronomeChecks[1] = metronomeChecks[2] = timeNow;
#endif
}

void resetButton(int idx)
{
  buttonIsPressed[idx] = false;
  buttonHeldStartTime[idx] = timeNow;
  buttonHeldState[idx] = false;
  buttonPressedDuration[idx] = 0;
  buttonIsPressedNow[idx] = false;
}

void resetAllButtonStates()
{
  resetButton(0);
  resetButton(1);
  resetButton(2);
}

void updateButtonState()
{
  for (int i = 0; i < 3; i++) {
    // Events/metronome take absolute priority so call once each loop just to make sure they're processed quickly
    if (playbackState == PLAYBACK_STARTED) {
      #if defined(INCLUDE_METRONOME) && defined(INCLUDE_REPLAYER)
      if (isMetronomeMode)
      #endif
      #if defined(INCLUDE_METRONOME)
        updateMetronome();
      #endif
      #if defined(INCLUDE_METRONOME) && defined(INCLUDE_REPLAYER)
      else
      #endif
      #if defined(INCLUDE_REPLAYER)
        updateEventHandler();
      #endif
    }
    
    bool previousPressState = buttonIsPressed[i];
    bool previousHeldState = buttonHeldState[i];
    bool curState = (*buttonPinPort[i] & buttonPinMask[i]) != 0;
    buttonIsPressedNow[i] = curState && buttonIsPressed[i] == false;
    buttonIsPressed[i] = curState;

    if (buttonIsPressedNow[i]) {
      buttonHeldStartTime[i] = timeNow;
    } else if (!buttonIsPressed[i] && previousPressState) {
      resetButton(i);
      buttonPressedDuration[i] = 0;
    }
    
    buttonPressedDuration[i] = timeNow - buttonHeldStartTime[i];
    buttonHeldState[i] = buttonIsPressed[i] && buttonPressedDuration[i] > 50000UL;
  }
}


void loop(void)
{      
  timeNow = micros();
  
  //if (playbackState != PLAYBACK_STARTED)
    updateButtonState();

#if defined(INCLUDE_METRONOME) && defined(INCLUDE_REPLAYER)
  if (buttonIsPressedNow[2]) {
    metronomeChecks[metronomeCheckIdx++] = timeNow;
    metronomeCheckIdx &= 3;

    unsigned long a = metronomeChecks[1] - metronomeChecks[0];
    unsigned long b = metronomeChecks[2] - metronomeChecks[1];
    
    if (a < MODE_SWITCH_DELAY_US && b < MODE_SWITCH_DELAY_US) {
      Serial.println("Switching modes!");
      isMetronomeMode = !isMetronomeMode;
      metronomeChecks[0] = 0;
      metronomeChecks[1] = MODE_SWITCH_DELAY_US + 1;
      metronomeChecks[2] = (MODE_SWITCH_DELAY_US * 2) + 1;
      metronomeCheckIdx = 0;
      playbackState = PLAYBACK_STOPPED;
      resetAllButtonStates();
    }
  }

  if (isMetronomeMode)
#endif
#ifdef INCLUDE_METRONOME
  {
    updateButtonStateMetronome();

    if (playbackState != PLAYBACK_STARTED) {
      updateScreenMetronome();
    }

    updateMetronome();
  }
#endif
#if defined(INCLUDE_METRONOME) && defined(INCLUDE_REPLAYER)
 else
#endif
#ifdef INCLUDE_REPLAYER
  {
    updateButtonStateChartReplay();

    if (playbackState == PLAYBACK_STARTED) {
      updateEventHandler();
    } else {
      updateScreenChartReplay();
    }
  }
#endif
}
