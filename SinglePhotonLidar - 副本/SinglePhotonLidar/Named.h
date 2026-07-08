#pragma pack(push,1)//把原来对齐方式设置压栈，并设置新的对齐方式为一个字节对齐;
#pragma once

struct LidarALLData
{
	/*uint8_t nFlag;
	uint8_t nChannel;
	uint32_t nPaulseNum;
	uint16_t nTimeInfo;
	uint8_t nClass;*/
	int nFlag;
	int nChannel;
	int nPaulseNum;
	int nTimeInfo;
	int nClass;
};

struct LidarCalData
{
	int nChannel;
	int nPaulseNum;
	int nTimeInfo;
	double dL;
	double dCodeNum;
	int nDate;
	double dSegTime;
};


struct LidarPt
{
	/*int nChannel;
	int nDate;
	int nTime;*/

	double X;
	double Y;
	double Z;
	double L;
};


struct LidarBLH
{
	double B;
	double L;
	double H;
};


struct POS
{
	double dTime;
	double dDistance;
	double dEasting;
	double dNorthing;
	double dEllipsoidHeight;
	double dLat;
	double dLong;
	double dHeight;
	double dRoll;			//Roll			翻滚角	Z
	double dPitch;			//Pitch			俯仰角	Y
	double dHeading;		//Yaw(Heading)	航向角	X
	double EastVelocity;
	double NorthVelocity;
	double UpVelocity;
	double EastSD;
	double NorthSD;
	double HeightSD;
	double RollSD;
	double PitchSD;
	double HeadingSD;
};

struct WFW
{
	int nEvent;
	double dTime;
	double dEasting;
	double dNorthing;
	double dHeight;
	double dOmega;
	double dPhi;
	double dKappa;
	double dLat;
	double dLong;
};



struct LidarPointCLoudA
{
	int nDate;
	double dSegTime;
	double dAngle;
	int nSingleZ;
	int nSingleA;
	int nChannel;
	int nPauseNum;
	double dL;

	double dX;
	double dY;
	double dZ;

	double dLat;
	double dLong;
	double dHeight;
	double dRoll;
	double dPitch;
	double dHeading;
	double dEasting;
	double dNorthing;
};


struct GroupItem {
	LidarALLData data;
	int index;
	double kmean_dist;
};

struct GroupStats {
	double mean;
	double stdev;
};

struct StatsMax 
{
	int nMaxLoc;
	double dMaxRange;
};

struct GaussPara
{
	double nPeak;	//振幅
	int nLocation;	//时刻
	double dSigma;	//波宽
};

#pragma pack(pop)//恢复对齐状态;