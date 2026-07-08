#pragma once
#include <iostream>
#include <iomanip>
#include<sstream>
#include <fstream>
#include <assert.h>
#include <vector>
#include <basetsd.h>
#include <string>
#include <math.h>
#include "Named.h"
#include "ByteTran.h"
using namespace std;

#define RANGE_MAX 1024
#define PI 3.1415926535898
#define C 299792458
#define  WGS84_a 6378137						//WGS84椭球长半轴
#define  WGS84_b 6356752.3142					//WGS84椭球短半轴
#define  WGS84_e1 0.0066943800042608			//WGS84椭球第一偏心率的平方
#define  WGS84_e2 0.0067394967565869			//WGS84椭球第二偏心率的平方
#define  WGS84_f 0.00335281067831240			//WGS84椭球扁率    1/f=298.25722235630016

int ReadSiglePhotonData(string strpath, vector<LidarALLData>&vAlldata);
vector<LidarALLData> ReadPhotonData(string istr);
int CalPauseCodeTime(vector<LidarALLData>vAlldata, LidarPointCLoudA *PtA);
int CalXYZ(vector<LidarCalData>vCaldata, vector<LidarPt>&vPt);
vector<POS> ReadPOS(string pos_path);
vector<WFW> ReadWFW(string pos_path);
LidarPt BLH2XYZ(LidarBLH blh);
LidarBLH XYZ2BLH(LidarPt xyz);
LidarPt BLH2UTM(LidarBLH blh, int nUTMZoneNum);
int CalPauseCodeTimeB(vector<LidarALLData>vAlldata, LidarPointCLoudA *PtA);
double StatisticLoc(vector<LidarALLData>vAlldata, double &dWinLoc);

void GaussFilt(double *sData, double *sData_FT, int nLen, int nR, int nSig, double &dMeanError);
void GaussDecompose(double *sData_FT, int nLen, int nStart, double dRandNoise, vector<GaussPara> &vGauss);
void SPL(int n, double *x, double *y, int ni, double *xi, double *yi);
void InterpSpline(vector<POS>vPOS, LidarPointCLoudA* &PtA, size_t sVecsize, int nChannel);