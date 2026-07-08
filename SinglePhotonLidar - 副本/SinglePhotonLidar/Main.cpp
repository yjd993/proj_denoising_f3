#include <iostream>
#include <fstream>
#include <string.h>
#include <stdio.h>
#include <iomanip>
#include<io.h>
#include <opencv2/opencv.hpp>

#include "ByteTran.h"
#include "Named.h"
#include "Function.h"
#include "FilterFunction.h"

using namespace std;
using namespace cv;




int main()
{
	/*string strInPath = "G:\\20200118\\1039_1st\\T3_2020_01_18_10_56_43_s30.dat";
	string strPosPath = "G:\\20200118\\APX-15\\POS_1_ASCII.txt";
	string strOutPath = "D:\\PC_NEH_CH1.txt";*/
	/*string strOutPath = "D:\\PC_NEH_CH1.txt";
	string strInPath = "G:\\20200617\\LinGang_泳池\\FLIGHT-03\\T3_2020_06_17_12_44_59_s55.dat";
	string strPosPath = "G:\\20200617\\POS_DATA_RTK\\eo_0617-03&04&05&06_ascII.txt";*/

	

	double dDeltaX, dDeltaY, dDeltaZ;
	dDeltaX = dDeltaY = dDeltaZ = 0;
	double dDeltaOmega, dDeltaPhi, dDeltaKappa;
	dDeltaOmega = dDeltaPhi = dDeltaKappa = 0;
	dDeltaOmega = 0;
	dDeltaPhi = 0;
	dDeltaKappa = 0;

	string strInPath;
	string strPosPath;
	cout << "FilePath: "; cin >> strInPath;
	cout << endl << "PosPath: "; cin >> strPosPath;
	int nChannel = 1;
	cout << "Channel (1-4) : "; cin >> nChannel;
	string strOutPath = strInPath;
	strOutPath.erase(0, strOutPath.find_last_of("\\") + 1);
	strOutPath = strOutPath.replace(strOutPath.find("."), 4, ".txt");
	cout << endl << "请输入安置偏差dDeltaX："; cin >> dDeltaX;
	cout << "请输入安置偏差dDeltaY："; cin >> dDeltaY;
	cout << "请输入安置偏差dDeltaZ："; cin >> dDeltaZ;
	cout << endl << "请输入安置偏差DeltaOMEGA："; cin >> dDeltaPhi;
	cout << "请输入安置偏差DeltaPHI："; cin >> dDeltaOmega;
	cout << "请输入安置偏差DeltaKAPPA："; cin >> dDeltaKappa;
	dDeltaOmega = dDeltaOmega * PI / 180.0;
	dDeltaPhi = dDeltaPhi * PI / 180.0;
	dDeltaKappa = dDeltaKappa * PI / 180.0;

	Mat mCd(3, 1, CV_64F);				//偏心距矩阵
	mCd.at<double>(0, 0) = dDeltaX;
	mCd.at<double>(1, 0) = dDeltaY;
	mCd.at<double>(2, 0) = dDeltaZ;

	double dCb1[9] = { 1,0,0,0,cos(dDeltaOmega),-sin(dDeltaOmega),0,sin(dDeltaOmega),cos(dDeltaOmega) };
	double dCb2[9] = { cos(dDeltaPhi),0,sin(dDeltaPhi),0,1,0,-sin(dDeltaPhi),0,cos(dDeltaPhi) };
	double dCb3[9] = { cos(dDeltaKappa),-sin(dDeltaKappa),0,sin(dDeltaKappa),cos(dDeltaKappa),0,0,0,1 };
	Mat mCb1(3, 3, CV_64F, dCb1);
	Mat mCb2(3, 3, CV_64F, dCb2);
	Mat mCb3(3, 3, CV_64F, dCb3);
	Mat mCb = mCb1 * mCb2 * mCb3;		//偏心角矩阵
	mCb1.release();
	mCb2.release();
	mCb3.release();



	vector<LidarALLData>vAlldata;
	vAlldata = ReadPhotonData(strInPath);//读取数据

	vector<POS>vPos;
	vPos = ReadPOS(strPosPath);			//读取POS
	cout << endl << "数据读取完成，正在处理。。。" << endl;
	
	double dLatMean = 0;
	double dLongMean = 0;
	for (size_t i = 0; i < vPos.size(); i++) {
		dLatMean += vPos[i].dLat;
		dLongMean += vPos[i].dLong;
	}
	dLatMean /= vPos.size();
	dLongMean /= vPos.size();

	double dWinLoc = 0;	//窗口回波
	double dUsuDis = 0;	//重影距离
	dUsuDis = StatisticLoc(vAlldata, dWinLoc);
	dUsuDis = 0;

	vector<LidarALLData>vFilterData;
	filter(vAlldata, vFilterData);
	//filter_mDBSCAN(vAlldata, vFilterData);
	vAlldata.clear();
	size_t sVecSize = vFilterData.size();
	LidarPointCLoudA *PtA = new LidarPointCLoudA[sVecSize]();
	CalPauseCodeTime(vFilterData, PtA);		//计算角度和时间


	ofstream ft;
	ft.open(strOutPath, ios::out);
	int nPosLoc = 0;
	bool bPos = false;

	for (size_t i = 0; i < sVecSize; i++)
	{
		if (PtA[i].nChannel == nChannel && PtA[i].dAngle > 0 && PtA[i].dSegTime > 0)
		{
			//POS内插
			for (size_t j = nPosLoc; j < vPos.size(); j++)
			{
				if (vPos[j].dLat == 0 || vPos[j].dLong == 0)
				{
					nPosLoc++;
					break;
				}

				int nPosHourT = (int)floor(vPos[j].dTime / 3600.0);
				int nPosHour = nPosHourT % 24;
				int nHour = nPosHourT - nPosHour;
				double dPosTime = vPos[j].dTime - nHour * 3600;
				double dt = abs(PtA[i].dSegTime - dPosTime);
				if (dt < 0.005)
				{
					nPosLoc = (int)j;
					bPos = true;
					break;
				}
			}
			if (bPos == true)
			{
				bPos = false;

				//本体坐标
				PtA[i].dL += dUsuDis - dWinLoc;
				double dPsi = (PtA[i].dAngle)*PI / 180.0;

				double dRx = 0.2564*sin(dPsi + 2.11) - 0.009696 - 0.007839*sin(2 * dPsi - 0.4963) - 7.808e-5*sin(4 * dPsi + 0.7918) - 0.0006754*sin(3 * dPsi + 0.9707);
				double dRy = 0.1817*sin(dPsi + 0.5428) + 0.01183*sin(2 * dPsi + 1.074) - 6.233e-5*sin(4 * dPsi - 0.4494) - 0.0003535*sin(3 * dPsi - 0.4003);
				double dRz = -sqrt(1 - pow(dRx, 2) - pow(dRy, 2));
				
				Mat m_Coords(3, 1, CV_64F);
				m_Coords.at<double>(0, 0) = PtA[i].dL *  dRy;
				m_Coords.at<double>(1, 0) = PtA[i].dL *  dRx;
				m_Coords.at<double>(2, 0) = -PtA[i].dL *  dRz;
				Mat m_CamPt = mCb * m_Coords + mCd;		//本体坐标（含偏心距和偏心角）


				double dHeading = (vPos[nPosLoc].dHeading)*PI / 180.0;
				double dPitch = vPos[nPosLoc].dPitch*PI / 180.0;
				double dRoll = vPos[nPosLoc].dRoll*PI / 180.0;
				double dCg[9] = {
				cos(dPitch)*cos(dHeading),sin(dRoll)*sin(dPitch)*cos(dHeading) - cos(dRoll)*sin(dHeading),cos(dRoll)*sin(dPitch)*cos(dHeading) + sin(dRoll)*sin(dHeading),
				cos(dPitch)*sin(dHeading),sin(dRoll)*sin(dPitch)*sin(dHeading) + cos(dRoll)*cos(dHeading),cos(dRoll)*sin(dPitch)*sin(dHeading) - sin(dRoll)*cos(dHeading),
				-sin(dPitch),sin(dRoll)*cos(dPitch),cos(dRoll)*cos(dPitch) };
				Mat mRg(3, 3, CV_64F, dCg);				//姿态角度矩阵

				LidarBLH blh;
				blh.B = vPos[nPosLoc].dLat*PI / 180.0;
				blh.L = vPos[nPosLoc].dLong*PI / 180.0;
				blh.H = vPos[nPosLoc].dHeight;

				double dRe[9] = {
					-cos(blh.L)*sin(blh.B),-sin(blh.L),-cos(blh.L)*cos(blh.B),
					-sin(blh.L)*sin(blh.B),cos(blh.L),-sin(blh.L)*cos(blh.B),
					cos(blh.B),0,-sin(blh.B) };
				Mat mRe(3, 3, CV_64F, dRe);				//经纬度矩阵

				LidarPt XYZ;
				XYZ = BLH2XYZ(blh);
				Mat mRc(3, 1, CV_64F);					//空间直角坐标
				mRc.at<double>(0, 0) = XYZ.X;
				mRc.at<double>(1, 0) = XYZ.Y;
				mRc.at<double>(2, 0) = XYZ.Z;

				double dB0 = dLatMean * PI / 180.0;
				double dL0 = dLongMean * PI / 180.0;
				double dCm[9] = {
					-sin(dB0)*cos(dL0),-sin(dB0)*sin(dL0),cos(dB0),
					-sin(dL0),cos(dL0),0,
					-cos(dL0)*cos(dB0),-cos(dB0)*sin(dL0),-sin(dB0) };
				Mat m_Cm(3, 3, CV_64F, dCm);

				Mat m_WGSpt = mRe * mRg * m_CamPt + mRc;
				//cout << mRc;

				LidarPt XYZpt;
				XYZpt.X = m_WGSpt.at<double>(0, 0);
				XYZpt.Y = m_WGSpt.at<double>(1, 0);
				XYZpt.Z = m_WGSpt.at<double>(2, 0);

				LidarBLH BLHpt;
				BLHpt = XYZ2BLH(XYZpt);

				LidarPt XYZ_UTM;
				XYZ_UTM = BLH2UTM(BLHpt, 51);

				PtA[i].dX = XYZ_UTM.X;
				PtA[i].dY = XYZ_UTM.Y;
				PtA[i].dZ = XYZ_UTM.Z;


				ft << setprecision(12) << PtA[i].dX << " " << PtA[i].dY << " " << PtA[i].dZ << " " << PtA[i].dL << " " << PtA[i].nPauseNum << endl;
			}

		}
	}


	////////////////////////////////////////////////////////////////////
	ft.close();
	delete[]PtA; PtA = NULL;
	cout << "点云生成成功！" << endl;
	system("pause");
	return 0;
}


