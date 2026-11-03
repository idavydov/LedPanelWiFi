"""Run the actual Arkanoid update routine with a host-side LED board."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_network_security import function

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / 'firmware/LedPanelWiFi_v1.14'


class ArkanoidTests(unittest.TestCase):
    def test_paddle_contact_has_no_empty_row_and_does_not_miss_fast_returns(self):
        source = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <algorithm>
#define SHELF_LENGTH 5
#define VELOCITY 5
constexpr uint32_t ARK_DEMO_ROUND_MS=5UL*60*1000;
uint32_t now=0,arkRoundStarted=0;
uint32_t millis() { return now; }
int sq(int n) { return n*n; }
int constrain(int n,int low,int high) { return std::max(low,std::min(n,high)); }
struct CRGB { enum { Black=0 }; };
const int GLOBAL_COLOR_1=1, GLOBAL_COLOR_2=2;
int pWIDTH=20,pHEIGHT=10;
int16_t posX_ark,posY_ark;
int8_t velX_ark,velY_ark,shelf_x=7;
int shelfMAX=15,buttons=4,deaths=0,ballX=-1,ballY=-1;
bool loadingFlag=false,gameDemo=false,gamePaused=false;
struct Timer { bool isReady() { return true; } } gameTimer,shelfTimer;
int board[20][10]={};
void drawPixelXY(int x,int y,int color) {
  if(x>=0 && x<pWIDTH && y>=0 && y<pHEIGHT) board[x][y]=color;
  if(color==GLOBAL_COLOR_1) { ballX=x; ballY=y; }
}
struct { void clear() {} } FastLED;
void FastLEDshow() {}
void delay(int) {}
bool checkButtons() { return false; }
void shelfLeft() {}
void shelfRight() {}
void newGameArkan() {}
void gameOverArkan() { ++deaths; posY_ark=15; posX_ark=100; arkRoundStarted=now; }
int blockX=-1,blockY=-1,hits=0;
int getPixColorXY(int x,int y) { return x==blockX && y==blockY ? 3 : 0; }
void redrawBlock(int x,int y) { assert(x==blockX && y==blockY); ++hits; blockX=blockY=-1; }
bool checkBlocks() { return false; }
'''
        game = (FIRMWARE / 'g_arkanoid.ino').read_text()
        source += function(game, 'void arkanoidRoutine(')
        source += r'''
void position(int y,int vy,int x=90,int vx=0) {
  posY_ark=y; velY_ark=vy; posX_ark=x; velX_ark=vx;
  ballX=ballY=-1;
}
int main() {
  position(24,-4); arkanoidRoutine();
  assert(posY_ark==20 && velY_ark==-4); // row 2 is too early to bounce
  arkanoidRoutine(); assert(ballY==1 && posY_ark==16 && velY_ark<0);
  arkanoidRoutine(); assert(ballY==1 && posY_ark==12 && velY_ark<0);
  arkanoidRoutine();
  assert(posY_ark==10 && ballY==1 && velY_ark>0 && deaths==0);
  assert(board[9][0]==GLOBAL_COLOR_2 && board[9][1]==GLOBAL_COLOR_1);
  arkanoidRoutine(); assert(velY_ark>0); // rising ball cannot bounce twice

  // Consecutive physical contacts must work even within the old 500 ms lockout.
  for(int i=0;i<3;++i) {
    position(13,-5); arkanoidRoutine();
    assert(posY_ark==10 && ballY==1 && velY_ark==5 && deaths==0);
  }
  position(14,-4); arkanoidRoutine(); assert(posY_ark==10 && velY_ark==4);
  position(10,-4); arkanoidRoutine(); assert(posY_ark==10 && velY_ark==4);

  // Both ends of the paddle remain inclusive/exclusive as expected.
  position(13,-4,74,-4); arkanoidRoutine();
  assert(posY_ark==10 && velX_ark==-4 && velY_ark>=3 && ballY==1);
  position(13,-4,106,4); arkanoidRoutine();
  assert(posY_ark==10 && velX_ark==4 && velY_ark>=3 && ballY==1);
  position(13,-4,120); arkanoidRoutine(); // immediately beyond right edge: miss
  assert(deaths==1 && ballY==-1); // stale coordinates must not be drawn after restart
  position(13,-4,60); arkanoidRoutine();
  assert(deaths==2 && ballY==-1);

  // The leftmost column must be hittable from column 1.
  position(46,4,14,-3); blockX=0; blockY=5;
  arkanoidRoutine();
  assert(hits==1 && velX_ark>0);

  // Only active computer-controlled rounds expire at five minutes.
  gameDemo=true; arkRoundStarted=1000; now=300999;
  position(40,4); arkanoidRoutine(); assert(deaths==2);
  now=301000; ballX=ballY=-1;
  arkanoidRoutine(); assert(deaths==3 && arkRoundStarted==now && ballY==-1);
  gameDemo=false; now+=ARK_DEMO_ROUND_MS;
  position(40,4); arkanoidRoutine(); assert(deaths==3);
  gameDemo=true; gamePaused=true; now+=ARK_DEMO_ROUND_MS;
  arkanoidRoutine(); assert(deaths==3);
  gamePaused=false;
  arkRoundStarted=UINT32_MAX-1000; now=1000;
  position(40,4); arkanoidRoutine(); assert(deaths==3); // timer wrap is not an expired round
  now=uint32_t(arkRoundStarted+ARK_DEMO_ROUND_MS);
  arkanoidRoutine(); assert(deaths==4);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'arkanoid.cpp'
            binary = Path(directory) / 'arkanoid'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
