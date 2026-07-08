#include "Function.h"
using namespace std;
//***********************************************************************//



int ReadSiglePhotonData(string strpath, vector<LidarALLData>&vAlldata)
{
	int nEvent_CH1[] = { 0,0,0,0,0,0,0 };		//0		CH1
	int nEvent_CH2[] = { 0,0,0,0,0,0,1 };		//1		CH2
	int nEvent_CH3[] = { 0,0,0,0,0,1,0 };		//2		CH3
	int nEvent_CH4[] = { 0,0,0,0,0,1,1 };		//3		CH4
	int nOutrangePaulse[] = { 1,1,1,1,1,1 };	//63	同步脉冲序号位溢出
	int nMarker1[] = { 0,0,0,0,0,1 };			//1		Marker1
	int nMarker2[] = { 0,0,0,0,1,0 };			//2		Marker2
	int nMarker3[] = { 0,0,0,1,0,0 };			//4		Marker3
	int nMarker4[] = { 0,0,1,0,0,0 };			//8		Marker4
	int nGPS_Header_Time[] = { 1,1,0,0,0 };		//24	GPS时间头
	int nGPS_Header_ALT[] = { 1,1,0,0,1 };		//25	经纬高度头
	int nGPS_Info_Time[] = { 1,0,0,0,0 };		//16	GPS时间信息
	int nGPS_Info_ALT[] = { 1,0,0,0,1 };		//17	经纬高度信息

	unsigned int nFill;
	unsigned int nFillstart = 3952129811;	//EB 90 B7 13
	unsigned int nFillend = 4008631773;		//EE EE DD DD
	int sync_ovfl_val = 0;					//溢出次数
	int sync_ovfl_ovfl_val = 0;				//溢出次数的次数

	const char *cpath = strpath.c_str();
	FILE *fp;
	fp = fopen(cpath, "rb");
	if (!fp) return -1;
	fseek(fp, 0, SEEK_END);
	unsigned long long lSize = ftell(fp);
	rewind(fp);
	unsigned long long lLoop = lSize / sizeof(int) - 1;


	fread(&nFill, sizeof(int), 1, fp);
	nFill = htonl(nFill);
	if (nFill != nFillstart)
	{
		fseek(fp, -4, SEEK_CUR);
		lLoop += 1;
	}

	//lLoop = 3000000;	//测试
	for (int nl = 0; nl < lLoop; nl++)
	{

		uint32_t t_nMSB;
		fread(&t_nMSB, 4, 1, fp);
		t_nMSB = htonl(t_nMSB);
		if (t_nMSB == nFillend)
			break;

		uint8_t t_nFlag = (t_nMSB >> 31);
		uint8_t t_nIndex_ChannalInfo = (t_nMSB << 1) >> 26;
		uint16_t t_nIndex_TimeInfo = (t_nMSB << 7) >> 17;
		uint32_t t_nIndex_PaulseNum = t_nMSB & 0x000003FF;


		LidarALLData Alldata{ 0 };					//存放栈
		Alldata.nFlag = t_nFlag;
		Alldata.nTimeInfo = t_nIndex_TimeInfo;
		Alldata.nPaulseNum = t_nIndex_PaulseNum;
		if (t_nFlag == 0)
		{
			if (sync_ovfl_val > 0)
			{
				t_nIndex_PaulseNum += sync_ovfl_val * RANGE_MAX + sync_ovfl_ovfl_val * RANGE_MAX;
				Alldata.nPaulseNum = t_nIndex_PaulseNum;
			}

			switch (t_nIndex_ChannalInfo)
			{
			case 0:
			{
				Alldata.nChannel = 1; //cout << "CH1" << endl;
				break;
			}
			case 1:
			{
				Alldata.nChannel = 2; //cout << "CH2" << endl;
				break;
			}
			case 2:
			{
				Alldata.nChannel = 3; //cout << "CH3" << endl;
				break;
			}
			case 3:
			{
				Alldata.nChannel = 4; //cout << "CH4" << endl;
				break;
			}
			default:
				Alldata.nFlag = 0;
				Alldata.nChannel = 0;
				Alldata.nPaulseNum = 0;
				Alldata.nTimeInfo = 0;
				break;
			}
		}
		else if (t_nFlag == 1)
		{
			switch (t_nIndex_ChannalInfo)
			{
			case 63:
			{
				if (sync_ovfl_val == RANGE_MAX - 1)
					sync_ovfl_ovfl_val++;
				sync_ovfl_val = t_nIndex_PaulseNum;
				if (sync_ovfl_ovfl_val > 0)
					sync_ovfl_val = RANGE_MAX - 1;

				Alldata.nChannel = 11;
				//cout << "OutRangePaulse" << endl;
				break;
			}
			case 1:
				Alldata.nChannel = 1; //cout << "Marker1" << endl;
				break;
			case 2:
				Alldata.nChannel = 2; //cout << "Marker2" << endl;
				break;
			case 4:
				Alldata.nChannel = 3; //cout << "Marker3" << endl;
				break;
			case 8:
				Alldata.nChannel = 4; //cout << "Marker4" << endl;
				break;
			case 24:
				Alldata.nChannel = 5; //cout << "GPSHeaderTime" << endl;
				break;
			case 25:
				Alldata.nChannel = 6; //cout << "GPSHeaderALT" << endl;
				break;
			case 16:
				Alldata.nChannel = 51; //cout << "GPSInfoTime" << endl;
				break;
			case 17:
				Alldata.nChannel = 61; //cout << "GPSInfoALT" << endl;
				break;
			default:
				Alldata.nFlag = 0;
				Alldata.nChannel = 0;
				Alldata.nPaulseNum = 0;
				Alldata.nTimeInfo = 0;
				break;
			}
		}
		vAlldata.push_back(Alldata);
	}
	fclose(fp);
	return 0;
}


vector<LidarALLData> ReadPhotonData(string istr)
{
	int nEvent_CH1[] = { 0,0,0,0,0,0,0 };		//0		CH1
	int nEvent_CH2[] = { 0,0,0,0,0,0,1 };		//1		CH2
	int nEvent_CH3[] = { 0,0,0,0,0,1,0 };		//2		CH3
	int nEvent_CH4[] = { 0,0,0,0,0,1,1 };		//3		CH4
	int nOutrangePaulse[] = { 1,1,1,1,1,1 };	//63	同步脉冲序号位溢出
	int nMarker1[] = { 0,0,0,0,0,1 };			//1		Marker1
	int nMarker2[] = { 0,0,0,0,1,0 };			//2		Marker2
	int nMarker3[] = { 0,0,0,1,0,0 };			//4		Marker3
	int nMarker4[] = { 0,0,1,0,0,0 };			//8		Marker4
	int nGPS_Header_Time[] = { 1,1,0,0,0 };		//24	GPS时间头
	int nGPS_Header_ALT[] = { 1,1,0,0,1 };		//25	经纬高度头
	int nGPS_Info_Time[] = { 1,0,0,0,0 };		//16	GPS时间信息
	int nGPS_Info_ALT[] = { 1,0,0,0,1 };		//17	经纬高度信息

	unsigned int nFill;
	unsigned int nFillstart = 3952129811;	//EB 90 B7 13
	unsigned int nFillend = 4008631773;		//EE EE DD DD
	int sync_ovfl_val = 0;					//溢出次数
	int sync_ovfl_ovfl_val = 0;				//溢出次数的次数

	vector<LidarALLData>vAlldata;
	ifstream fin;
	fin.open(istr, ios::binary);
	if (!fin) exit(0);
	fin.seekg(0, ios::end);
	unsigned long long lSize = fin.tellg();
	fin.seekg(0, ios::beg);
	unsigned long long lLoop = lSize / sizeof(int) - 1;

	fin.read((char*)&nFill, 4);
	nFill = htonl(nFill);
	if (nFill != nFillstart)
	{
		fin.seekg(-4, ios::cur);
		lLoop += 1;
	}

	for (int nl = 0; nl < lLoop; nl++)
	{

		uint32_t t_nMSB;
		fin.read((char*)&t_nMSB, sizeof(int));
		t_nMSB = htonl(t_nMSB);
		if (t_nMSB == nFillend)
			break;

		uint8_t t_nFlag = (t_nMSB >> 31);
		uint8_t t_nIndex_ChannalInfo = (t_nMSB << 1) >> 26;
		uint16_t t_nIndex_TimeInfo = (t_nMSB << 7) >> 17;
		uint32_t t_nIndex_PaulseNum = t_nMSB & 0x000003FF;


		LidarALLData Alldata{ 0 };					//存放栈
		Alldata.nFlag = t_nFlag;
		Alldata.nTimeInfo = t_nIndex_TimeInfo;
		Alldata.nPaulseNum = t_nIndex_PaulseNum;
		if (t_nFlag == 0)
		{
			if (sync_ovfl_val > 0)
			{
				t_nIndex_PaulseNum += sync_ovfl_val * RANGE_MAX + sync_ovfl_ovfl_val * RANGE_MAX;
				Alldata.nPaulseNum = t_nIndex_PaulseNum;
			}

			switch (t_nIndex_ChannalInfo)
			{
			case 0:
			{
				Alldata.nChannel = 1; //cout << "CH1" << endl;
				break;
			}
			case 1:
			{
				Alldata.nChannel = 2; //cout << "CH2" << endl;
				break;
			}
			case 2:
			{
				Alldata.nChannel = 3; //cout << "CH3" << endl;
				break;
			}
			case 3:
			{
				Alldata.nChannel = 4; //cout << "CH4" << endl;
				break;
			}
			default:
				Alldata.nFlag = 0;
				Alldata.nChannel = 0;
				Alldata.nPaulseNum = 0;
				Alldata.nTimeInfo = 0;
				break;
			}
		}
		else if (t_nFlag == 1)
		{
			switch (t_nIndex_ChannalInfo)
			{
			case 63:
			{
				if (sync_ovfl_val == RANGE_MAX - 1)
					sync_ovfl_ovfl_val++;
				sync_ovfl_val = t_nIndex_PaulseNum;
				if (sync_ovfl_ovfl_val > 0)
					sync_ovfl_val = RANGE_MAX - 1;

				Alldata.nChannel = 11;
				//cout << "OutRangePaulse" << endl;
				break;
			}
			case 1:
				Alldata.nChannel = 1; //cout << "Marker1" << endl;
				break;
			case 2:
				Alldata.nChannel = 2; //cout << "Marker2" << endl;
				break;
			case 4:
				Alldata.nChannel = 3; //cout << "Marker3" << endl;
				break;
			case 8:
				Alldata.nChannel = 4; //cout << "Marker4" << endl;
				break;
			case 24:
				Alldata.nChannel = 5; //cout << "GPSHeaderTime" << endl;
				break;
			case 25:
				Alldata.nChannel = 6; //cout << "GPSHeaderALT" << endl;
				break;
			case 16:
				Alldata.nChannel = 51; //cout << "GPSInfoTime" << endl;
				break;
			case 17:
				Alldata.nChannel = 61; //cout << "GPSInfoALT" << endl;
				break;
			default:
				Alldata.nFlag = 0;
				Alldata.nChannel = 0;
				Alldata.nPaulseNum = 0;
				Alldata.nTimeInfo = 0;
				break;
			}
		}
		vAlldata.push_back(Alldata);
	}
	fin.close();
	return vAlldata;
}

//***********************************************************************//



int CalPauseCodeTime(vector<LidarALLData>vAlldata, LidarPointCLoudA *PtA)
{
	size_t sVecSize = vAlldata.size();
	//角度
	double dM2CodeNum = 0.0;		//在一个Z相信号中，每个A相信号的码盘读数(4096?)
	bool bCirM2 = false;			//第一圈Z相
	bool bCirM3 = false;			//第一圈A相
	int nM2_start = 0;				//Z相信号中，光子的起点
	int nM2_end = 0;				//Z相信号中，光子的终点
	int nM2_num = 0;				//在一个Z相信号中，有多少个A相信号
	int nM3_start = 0;				//A相信号中，光子的起点
	int nM3_end = 0;				//A相信号中，光子的终点
	int nNum_M3 = 0;				//A相信号中有多少个脉冲序列号
	int nnM2 = 0;					//第几圈Z相信号
	int nnM3 = 0;					//第几圈A相信号
	int nM2_num_old = 0;			//判断A相重复信号
	int nM3_paulse = 0;				//Z相信号脉冲数
	int nMst_start = 0;
	int nMst_end = 0;

	for (size_t i = 0; i < sVecSize; i++)
	{
		if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 2 && bCirM2 == true)
		{
			nM2_end = (int)i;
			int nM2_E_S = nM2_end - nM2_start;
			if (nM2_E_S > 50)
			{
				//cout << nM2_E_S <<" "<< nM2_num << endl;
				dM2CodeNum = 360.0 / nM2_num;
				nnM2++;
				nnM3 = 0;
				nM3_paulse = 0;
				nMst_end = (int)i;

				double dCodeSum = 0.0;		//当前光子码盘读数
				double dCodeTemp = 0.0;		//每个光子在A相之间码盘读数
				for (int j = nM2_start; j < nM2_end; j++)
				{
					if (vAlldata[j].nFlag == 1 && vAlldata[j].nChannel == 3 && bCirM3 == true)
					{
						nM3_end = j;
						nnM3++;

						int nn1 = vAlldata[nM3_start].nPaulseNum;	//A相第一个序列号
						int nn2 = vAlldata[nM3_end].nPaulseNum;		//A相最后一个序列号
						int m = 0;
						//cout << nn1 << " " << nn2 << endl;
						while (vAlldata[nM3_start + m].nFlag == 1)
						{
							m++;
							nn1 = vAlldata[nM3_start + m].nPaulseNum;
							if (nM3_start + m >= nM3_end)break;
						}
						m = 0;
						while (vAlldata[nM3_end - m].nFlag == 1)
						{
							m++;
							nn2 = vAlldata[nM3_end - m].nPaulseNum;
							if (nM3_end - m <= nM3_start)break;
						}
						nNum_M3 = nn2 - nn1;
						//cout << nn1<<" "<<nn2<<" "<<nNum_M3 << endl;
						if (nn1 == nn2 && nn1 != 0)nNum_M3 = 1;
						if (nNum_M3 > 0)
						{
							nM3_paulse += nNum_M3;
							dCodeTemp = dM2CodeNum / nNum_M3;
							int nb = 1;									//每个A相信号角度的倍数
							for (int k = 0; k < (nM3_end - nM3_start); k++)
							{
								if (vAlldata[nM3_start + k].nPaulseNum == nn1)
								{
									PtA[nM3_start + k].dAngle = dCodeSum + dCodeTemp * nb;
									PtA[nM3_start + k].nSingleZ = nnM2;
									PtA[nM3_start + k].nSingleA = nnM3;
								}
								else if (vAlldata[nM3_start + k].nPaulseNum > nn1)
								{
									nb++;
									nn1++;
									k--;
								}
							}
						}
						dCodeSum += dM2CodeNum;
						nM3_start = nM3_end;
					}
					else if (vAlldata[j].nFlag == 1 && vAlldata[j].nChannel == 3 && bCirM3 == false)
					{
						nM3_start = j;
						bCirM3 = true;
					}

				}
				//cout << nM3_paulse << endl;
			}
			nM2_start = nM2_end;
			nM2_num = 0;
		}
		else if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 2 && bCirM2 == false)
		{
			nM2_num = 0;
			nM2_start = (int)i;
			bCirM2 = true;
			nMst_start = (int)i;
		}

		if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 3)
		{
			nM2_num++;
			if (abs((int)i - nM2_num_old) < 2)
				nM2_num--;
			nM2_num_old = (int)i;
		}


	}

	//cout << nMst_start << " " << nMst_end << endl;
	//cout << sVecSize;
	/*double dCodeSum = 0;
	bCirM3 = false;
	for (int j = 0; j < nMst_start; j++) {
		if (vAlldata[j].nFlag == 1 && vAlldata[j].nChannel == 3 && bCirM3 == true)
		{
			nM3_end = j;
			nnM3++;

			int nn1 = vAlldata[nM3_start].nPaulseNum;	//A相第一个序列号
			int nn2 = vAlldata[nM3_end].nPaulseNum;		//A相最后一个序列号
			int m = 0;
			//cout << nn1 << " " << nn2 << endl;

			while (vAlldata[nM3_start + m].nFlag == 1)
			{
				m++;
				nn1 = vAlldata[nM3_start + m].nPaulseNum;
				if (nM3_start + m >= nM3_end)break;
			}
			m = 0;
			while (vAlldata[nM3_end - m].nFlag == 1)
			{
				m++;
				nn2 = vAlldata[nM3_end - m].nPaulseNum;
				if (nM3_end - m <= nM3_start)break;
			}
			nNum_M3 = nn2 - nn1;
			//cout << nn1<<" "<<nn2<<" "<<nNum_M3 << endl;
			if (nn1 == nn2 && nn1 != 0)nNum_M3 = 1;
			if (nNum_M3 > 0)
			{
				nM3_paulse += nNum_M3;
				double dCodeTemp = dM2CodeNum / nNum_M3;
				int nb = 1;									//每个A相信号角度的倍数
				for (int k = 0; k < (nM3_end - nM3_start); k++)
				{
					if (vAlldata[nM3_start + k].nPaulseNum == nn1)
					{
						PtA[nM3_start + k].dAngle = dCodeSum + dCodeTemp * nb;
						PtA[nM3_start + k].nSingleZ = nnM2;
						PtA[nM3_start + k].nSingleA = nnM3;
					}
					else if (vAlldata[nM3_start + k].nPaulseNum > nn1)
					{
						nb++;
						nn1++;
						k--;
					}
				}
			}
			dCodeSum += dM2CodeNum;
			nM3_start = nM3_end;
		}
		else if (vAlldata[j].nFlag == 1 && vAlldata[j].nChannel == 3 && bCirM3 == false)
		{
			nM3_start = j;
			bCirM3 = true;
		}
	}

	bCirM3 = false;
	dCodeSum = 0;
	for (size_t j = sVecSize-1; j > nMst_end; j--) {
		if (vAlldata[j].nFlag == 1 && vAlldata[j].nChannel == 3 && bCirM3 == true)
		{
			nM3_start = (int)j;
			nnM3++;
			//cout << nM3_start << " " << nM3_end << " "<<sVecSize<<" "<<nMst_end<<endl;

			int nn1 = vAlldata[nM3_start].nPaulseNum;	//A相第一个序列号
			int nn2 = vAlldata[nM3_end].nPaulseNum;		//A相最后一个序列号
			int m = 0;
			//cout << nn1 << " " << nn2 << endl;

			while (vAlldata[nM3_start + m].nFlag == 1)
			{
				m++;
				nn1 = vAlldata[nM3_start + m].nPaulseNum;
				if (nM3_start + m >= nM3_end)break;
			}
			m = 0;
			while (vAlldata[nM3_end - m].nFlag == 1)
			{
				m++;
				nn2 = vAlldata[nM3_end - m].nPaulseNum;
				if (nM3_end - m <= nM3_start)break;
			}
			nNum_M3 = nn2 - nn1;
			//cout << nn1<<" "<<nn2<<" "<<nNum_M3 << endl;
			if (nn1 == nn2 && nn1 != 0)nNum_M3 = 1;
			if (nNum_M3 > 0)
			{
				nM3_paulse += nNum_M3;
				double dCodeTemp = dM2CodeNum / nNum_M3;
				int nb = 1;									//每个A相信号角度的倍数
				for (int k = 0; k < (nM3_end - nM3_start); k++)
				{
					if (vAlldata[nM3_start + k].nPaulseNum == nn1)
					{
						PtA[nM3_start + k].dAngle = dCodeSum + dCodeTemp * nb;
						PtA[nM3_start + k].nSingleZ = nnM2;
						PtA[nM3_start + k].nSingleA = nnM3;
					}
					else if (vAlldata[nM3_start + k].nPaulseNum > nn1)
					{
						nb++;
						nn1++;
						k--;
					}
				}
			}
			dCodeSum += dM2CodeNum;
			nM3_end = nM3_start;
		}
		else if (vAlldata[j].nFlag == 1 && vAlldata[j].nChannel == 3 && bCirM3 == false)
		{
			nM3_end = (int)j;
			bCirM3 = true;
		}
	}*/
	//******************************************//

	//时间
	int nT1, nT2, nT3;
	nT1 = nT2 = nT3 = 0;
	double dT = 0;
	int nt = 0;
	bool bT = false;
	bool bCirM1 = false;
	int nM1_start = 0;
	int nM1_end = 0;
	int nNum_M1 = 0;
	nMst_start = 0;
	nMst_end = 0;

	for (size_t i = 0; i < sVecSize; i++)
	{
		if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 51)
		{
			bT = true;
			nt++;
			int ntemp1[15], ntemp2[10], ntemp[25];
			dec2bin(vAlldata[i].nTimeInfo, ntemp1, 15);
			dec2bin(vAlldata[i].nPaulseNum, ntemp2, 10);
			for (int i = 0; i < 15; i++)
				ntemp[i] = ntemp1[i];
			for (int i = 0; i < 10; i++)
				ntemp[i + 15] = ntemp2[i];

			int nhex = bin2dec(ntemp, 25);
			string shex = dec2hex(nhex);
			stringstream sshex;
			sshex << shex;

			if (nt == 1)
			{
				//nT1 = stoi(shex);
				sshex >> nT1;
				nT1 += 20000000;
			}
			if (nt == 2)
			{
				if (shex == "")
					nT2 = 0;
				else
				{
					//nT2 = stoi(shex);
					sshex >> nT2;
					int nT2hour = nT2 / 10000;
					int nT2Min = (nT2 - nT2hour * 10000) / 100;
					int nT2Sec = nT2 - nT2hour * 10000 - nT2Min * 100;
					nT2 = nT2hour * 3600 + nT2Min * 60 + nT2Sec;
				}
			}
			if (nt == 3)
			{
				if (shex == "")
					nT3 = 0;
				else
					sshex >> nT3;
					//nT3 = stoi(shex);
				dT = nT2;// +(double)nT3*0.001;
				nt = 0;
			}

		}
		if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 1 && bCirM1 == true)
		{
			nM1_end = (int)i;

			int nn1 = vAlldata[nM1_start].nPaulseNum;	//PPS第一个序列号
			int nn2 = vAlldata[nM1_end].nPaulseNum;		//PPS最后一个序列号
			int m = 0;
			while (vAlldata[nM1_start + m].nFlag == 1)
			{
				m++;
				nn1 = vAlldata[nM1_start + m].nPaulseNum;
			}
			m = 0;
			while (vAlldata[nM1_end - m].nFlag == 1)
			{
				m++;
				nn2 = vAlldata[nM1_end - m].nPaulseNum;
			}
			nNum_M1 = nn2 - nn1;
			//cout << nNum_M1 << endl;
			int nb = 1;
			for (int j = 0; j < (nM1_end - nM1_start); j++)
			{
				if (vAlldata[nM1_start + j].nPaulseNum == nn1 && bT == true)
				{
					PtA[nM1_start + j].dSegTime = dT + nb / (double)nNum_M1 + 18;	//2019	UTC -> GPS time
					PtA[nM1_start + j].nDate = nT1;
				}
				if (vAlldata[nM1_start + j].nPaulseNum > nn1)
				{
					nb++;
					nn1++;
					j--;
				}
			}
			nM1_start = nM1_end;
			nMst_end = (int)i;
		}
		else if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 1 && bCirM1 == false)
		{
			nM1_start = (int)i;
			bCirM1 = true;
			nMst_start = (int)i;
		}

	}




	//补齐时间
	int m = 0;
	int nn1 = vAlldata[nMst_end].nPaulseNum;
	while (vAlldata[nMst_end + m].nFlag == 1)
	{
		m++;
		nn1 = vAlldata[nMst_end + m].nPaulseNum;
	}
	int nb = 1;
	for (int j = 0; j < ((int)sVecSize - nMst_end); j++)
	{
		if (vAlldata[nMst_end + j].nPaulseNum == nn1 && bT == true)
		{
			PtA[nMst_end + j].dSegTime = dT + nb / (double)nNum_M1 + 18;	//2019	UTC -> GPS time
			PtA[nMst_end + j].nDate = nT1;
		}
		if (vAlldata[nMst_end + j].nPaulseNum > nn1)
		{
			nb++;
			nn1++;
			j--;
		}
	}

	m = 0;
	int nn2 = 0;
	while (vAlldata[nMst_start + m].nFlag == 1)
	{
		m++;
		nn2 = vAlldata[nMst_start + m].nPaulseNum;
	}

	//cout << nn2 <<" "<<PtA[nMst_start+m].dSegTime<<endl;
	nb = 1;
	int nc = nMst_start + m;
	for (int j = nMst_start+m-1; j > 0; j--) {
		if (vAlldata[j].nPaulseNum == nn2) {
			PtA[j].dSegTime = PtA[nc].dSegTime - nb / (double)nNum_M1;
			PtA[j].nDate = PtA[nMst_start + m].nDate;
			//cout << j<<" "<<vAlldata[j].nPaulseNum<<" "<< setprecision(12)<<PtA[j].dSegTime << endl;
		}

		if (vAlldata[j].nPaulseNum < nn2 && vAlldata[j].nPaulseNum!=0 && vAlldata[j].nFlag!=1)
		{
			nb++;
			nn2--;
			j++;
		}

	}
	//**********************************//







	for (size_t i = 0; i < sVecSize; i++)
	{
		PtA[i].nChannel = vAlldata[i].nChannel;
		PtA[i].nPauseNum = vAlldata[i].nPaulseNum;
		PtA[i].dL = vAlldata[i].nTimeInfo* 64e-12 * C / 2.0;
	}

	return 0;
}

int CalPauseCodeTimeB(vector<LidarALLData>vAlldata, LidarPointCLoudA *PtA)
{
	size_t sVecSize = vAlldata.size();
	//角度
	double dM2CodeNum = 0.0;		//在一个Z相信号中，每个A相信号的码盘读数(4096?)
	bool bCirM2 = false;			//第一圈Z相
	bool bCirM3 = false;			//第一圈A相
	int nM2_start = 0;				//Z相信号中，光子的起点
	int nM2_end = 0;				//Z相信号中，光子的终点
	int nM2_num = 0;				//在一个Z相信号中，有多少个A相信号
	int nM3_start = 0;				//A相信号中，光子的起点
	int nM3_end = 0;				//A相信号中，光子的终点
	int nNum_M3 = 0;				//A相信号中有多少个脉冲序列号
	int nnM2 = 0;					//第几圈Z相信号
	int nnM3 = 0;					//第几圈A相信号
	int nM2_num_old = 0;			//判断A相重复信号
	int nM3_paulse = 0;				//Z相信号脉冲数

	for (size_t i = 0; i < sVecSize; i++)
	{
		if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 2 && bCirM2 == true)
		{
			nM2_end = (int)i;
			int nM2_E_S = nM2_end - nM2_start;
			if (nM2_E_S > 50)
			{
				//cout << nM2_E_S << " " << nM2_num << endl;
				dM2CodeNum = 360.0 / nM2_num;
				nnM2++;
				nnM3 = 0;
				nM3_paulse = 0;

				double dCodeSum = 0.0;		//当前光子码盘读数
				double dCodeTemp = 0.0;		//每个光子在A相之间码盘读数
				for (int j = nM2_start; j < nM2_end; j++)
				{
					if (vAlldata[j].nFlag == 1 && vAlldata[j].nChannel == 4 && bCirM3 == true)
					{
						nM3_end = j;
						nnM3++;

						int nn1 = vAlldata[nM3_start].nPaulseNum;	//A相第一个序列号
						int nn2 = vAlldata[nM3_end].nPaulseNum;		//A相最后一个序列号
						int m = 0;
						while (vAlldata[nM3_start + m].nFlag == 1)
						{
							m++;
							nn1 = vAlldata[nM3_start + m].nPaulseNum;
							if (nM3_start + m >= nM3_end)break;
						}
						m = 0;
						while (vAlldata[nM3_end - m].nFlag == 1)
						{
							m++;
							nn2 = vAlldata[nM3_end - m].nPaulseNum;
							if (nM3_end - m <= nM3_start)break;
						}
						nNum_M3 = nn2 - nn1;
						if (nn1 == nn2 && nn1 != 0)nNum_M3 = 1;
						if (nNum_M3 > 0)
						{
							nM3_paulse += nNum_M3;
							dCodeTemp = dM2CodeNum / nNum_M3;
							int nb = 1;									//每个A相信号角度的倍数
							for (int k = 0; k < (nM3_end - nM3_start); k++)
							{
								if (vAlldata[nM3_start + k].nPaulseNum == nn1)
								{
									PtA[nM3_start + k].dAngle = dCodeSum + dCodeTemp * nb;
									PtA[nM3_start + k].nSingleZ = nnM2;
									PtA[nM3_start + k].nSingleA = nnM3;
								}
								else if (vAlldata[nM3_start + k].nPaulseNum > nn1)
								{
									nb++;
									nn1++;
									k--;
								}
							}
						}
						dCodeSum += dM2CodeNum;
						nM3_start = nM3_end;
					}
					else if (vAlldata[j].nFlag == 1 && vAlldata[j].nChannel == 4 && bCirM3 == false)
					{
						nM3_start = j;
						bCirM3 = true;
					}

				}
				//cout << nM3_paulse << endl;
			}
			nM2_start = nM2_end;
			nM2_num = 0;
		}
		else if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 2 && bCirM2 == false)
		{
			nM2_num = 0;
			nM2_start = (int)i;
			bCirM2 = true;
		}
		if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 4)
		{
			nM2_num++;
			if (abs((int)i - nM2_num_old) < 2)
				nM2_num--;
			nM2_num_old = (int)i;
		}

	}


	//时间
	int nT1, nT2, nT3;
	nT1 = nT2 = nT3 = 0;
	double dT = 0;
	int nt = 0;
	bool bT = false;
	bool bCirM1 = false;
	int nM1_start = 0;
	int nM1_end = 0;
	int nNum_M1 = 0;
	for (size_t i = 0; i < sVecSize; i++)
	{
		if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 51)
		{
			bT = true;
			nt++;
			int ntemp1[15], ntemp2[10], ntemp[25];
			dec2bin(vAlldata[i].nTimeInfo, ntemp1, 15);
			dec2bin(vAlldata[i].nPaulseNum, ntemp2, 10);
			for (int i = 0; i < 15; i++)
				ntemp[i] = ntemp1[i];
			for (int i = 0; i < 10; i++)
				ntemp[i + 15] = ntemp2[i];

			int nhex = bin2dec(ntemp, 25);
			string shex = dec2hex(nhex);

			if (nt == 1)
			{
				nT1 = stoi(shex);
				nT1 += 20000000;
			}
			if (nt == 2)
			{
				if (shex == "")
					nT2 = 0;
				else
				{
					nT2 = stoi(shex);
					int nT2hour = nT2 / 10000;
					int nT2Min = (nT2 - nT2hour * 10000) / 100;
					int nT2Sec = nT2 - nT2hour * 10000 - nT2Min * 100;
					nT2 = nT2hour * 3600 + nT2Min * 60 + nT2Sec;
				}
			}
			if (nt == 3)
			{
				if (shex == "")
					nT3 = 0;
				else
					nT3 = stoi(shex);
				dT = nT2 + (double)nT3*0.001;
				nt = 0;
			}

		}
		if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 1 && bCirM1 == true)
		{
			nM1_end = (int)i;

			int nn1 = vAlldata[nM1_start].nPaulseNum;	//PPS第一个序列号
			int nn2 = vAlldata[nM1_end].nPaulseNum;		//PPS最后一个序列号
			int m = 0;
			while (vAlldata[nM1_start + m].nFlag == 1)
			{
				m++;
				nn1 = vAlldata[nM1_start + m].nPaulseNum;
			}
			m = 0;
			while (vAlldata[nM1_end - m].nFlag == 1)
			{
				m++;
				nn2 = vAlldata[nM1_end - m].nPaulseNum;
			}
			nNum_M1 = nn2 - nn1;
			int nb = 1;
			for (int j = 0; j < (nM1_end - nM1_start); j++)
			{
				if (vAlldata[nM1_start + j].nPaulseNum == nn1 && bT == true)
				{
					PtA[nM1_start + j].dSegTime = dT + nb / (double)nNum_M1;
					PtA[nM1_start + j].nDate = nT1;
				}
				if (vAlldata[nM1_start + j].nPaulseNum > nn1)
				{
					nb++;
					nn1++;
					j--;
				}
			}
			nM1_start = nM1_end;
		}
		else if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 1 && bCirM1 == false)
		{
			nM1_start = (int)i;
			bCirM1 = true;
		}

	}

	for (size_t i = 0; i < sVecSize; i++)
	{
		if (PtA[i].dSegTime > 0 && PtA[i].dAngle > 0 && PtA[i].nChannel == 1) {
			PtA[i].nChannel = vAlldata[i].nChannel;
			PtA[i].nPauseNum = vAlldata[i].nPaulseNum;
			PtA[i].dL = vAlldata[i].nTimeInfo*0.000000000001 * 64 * C / 2.0;
		}
	}

	return 0;
}

int CalXYZ(vector<LidarCalData>vCaldata, vector<LidarPt>&vPt)
{
	LidarPt Pt;

	for (size_t i = 0; i < vCaldata.size(); i++)
	{
		if (vCaldata[i].dCodeNum > 0 && vCaldata[i].dSegTime != 0 && vCaldata[i].nTimeInfo != 0)
		{
			double dPsi = vCaldata[i].dCodeNum*PI / 180.0;
			double dVectorNormalRaypath1 = (2.5033e66*pow(cos(dPsi), 2.0) - 1.3571e67*cos(dPsi) +
				4.4718e65*pow(cos(dPsi), 4.0) + 8.786e65) / ((1.3124e67*cos(dPsi) + 8.6388e65*pow(cos(dPsi), 2.0) - 5.157e67));
			double dVectorNormalRaypath2 = (1.1697e66*sin(2.0*dPsi) + 5.2036e63*sin(4.0*dPsi) + 2.3715e65*sin(3.0*dPsi) -
				1.8639e67*sin(dPsi)) / (2.6247e67*cos(dPsi) + 1.7278e66*pow(cos(dPsi), 2.0) - 1.0314e68);
			double dVectorNormalRaypath3 = (8.9436e64*pow(cos(dPsi), 3.0) - 6.9111e65*pow(cos(dPsi), 2.0) - 5.16e66*cos(dPsi) +
				5.8872e63*pow(cos(dPsi), 4.0) + 2.0277e67) / (5.2495e66*cos(dPsi) + 3.4555e65*pow(cos(dPsi), 2.0) - 2.0628e67);

			double dD = vCaldata[i].nTimeInfo*pow(10, -12) * 64 * C / 2.0;
			Pt.X = dD * dVectorNormalRaypath1;
			Pt.Y = dD * dVectorNormalRaypath2;
			Pt.Z = -dD * dVectorNormalRaypath3;
			Pt.L = dD;
			vPt.push_back(Pt);
		}		

	}
	return 0;
}



vector<POS> ReadPOS(string pos_path)
{
	vector<POS> pos_data;
	ifstream pos_file_stream(pos_path);
	stringstream pos_buffer;
	pos_buffer << pos_file_stream.rdbuf();
	string start_marker = "  (time in Sec, distance in Meters, position in Meters, lat, long in Degrees, orientation angles and SD in Degrees, velocity in Meter/Sec, position SD in Meters)  ";
	bool start_flag = false;
	string line;
	while (getline(pos_buffer, line))
	{
		if (!start_flag)
		{
			if (line.compare(start_marker) == 0)
			{
				start_flag = true;
				continue;
			}
		}
		else
		{
			if (line.length() == 0)
			{
				continue;
			}
			stringstream rs(line);
			POS pos = { 0 };
			// TIME, DISTANCE, EASTING, NORTHING, ELLIPSOID HEIGHT, LATITUDE, LONGITUDE, ELLIPSOID HEIGHT, ROLL, PITCH, HEADING, EAST VELOCITY, NORTH VELOCITY, UP VELOCITY, EAST SD, NORTH SD, HEIGHT SD, ROLL SD, PITCH SD, HEADING SD
			rs >> pos.dTime >> pos.dDistance >> pos.dEasting >> pos.dNorthing >> pos.dEllipsoidHeight
				>> pos.dLat >> pos.dLong >> pos.dHeight >> pos.dRoll >> pos.dPitch >> pos.dHeading
				>> pos.EastVelocity >> pos.NorthVelocity >> pos.UpVelocity >> pos.EastSD >> pos.NorthSD
				>> pos.HeightSD >> pos.RollSD >> pos.PitchSD >> pos.HeadingSD;
			pos_data.push_back(pos);
		}
	}
	return pos_data;
}

vector<WFW> ReadWFW(string pos_path)
{
	vector<WFW> pos_data;
	ifstream pos_file_stream(pos_path);
	stringstream pos_buffer;
	pos_buffer << pos_file_stream.rdbuf();
	string start_marker = " ID, # EVENT, TIME (s), EASTING, NORTHING, ELLIPSOID HEIGHT, OMEGA, PHI, KAPPA, LAT, LONG";
	bool start_flag = false;
	string line;
	while (getline(pos_buffer, line))
	{
		if (!start_flag)
		{
			if (line.compare(start_marker) == 0)
			{
				start_flag = true;
				continue;
			}
		}
		else
		{
			if (line.length() == 0)
			{
				continue;
			}
			stringstream rs(line);
			WFW pos = { 0 };
			rs >> pos.nEvent >> pos.dTime >> pos.dEasting >> pos.dNorthing >> pos.dHeight >> pos.dOmega >>
				pos.dPhi >> pos.dKappa >> pos.dLat >> pos.dLong;
			if (pos.dLat != 0 && pos.dLong != 0)
				pos_data.push_back(pos);
		}
	}
	return pos_data;
}


LidarPt BLH2XYZ(LidarBLH blh)
{
	LidarPt xyz;
	double W;
	double N;
	/*blh.B = blh.B*PI / 180.0;
	blh.L = blh.L*PI / 180.0;*/

	W = sqrt(1 - WGS84_e1 * pow(sin(blh.B), 2));
	N = WGS84_a / W;

	xyz.X = (N + blh.H)*cos(blh.B)*cos(blh.L);
	xyz.Y = (N + blh.H)*cos(blh.B)*sin(blh.L);
	xyz.Z = (N*(1 - WGS84_e1) + blh.H)*sin(blh.B);
	return xyz;
}


LidarPt BLH2UTM(LidarBLH blh, int nUTMZoneNum)
{
	LidarPt utm{ 0 };
	double W;
	double V;												//椭球的卯酉圈曲率半径 V=a/W
	double dUTM_k0;											//中央子午线比例系数
	double dDertaNumda;										//当地经度与中央子午线的差值，单位：秒
	double dCenterLongitude;								//该投影区域的中心经度
	double dLocalLongitude;									//该点已知的经度
	double dLocalLatitude;									//该点已知的纬度
	double dP;
	double dn;
	double dA1, dB1, dC1, dD1, dE1;
	double dS, dT3, dT4, dT8;
	double dSin1miao;										//sin(1'')
	double dPosN, dPosE;									//UTM北坐标和东坐标
	double dFalseEasting;									//UTM坐标系统东移假定值

	W = sqrt(1 - WGS84_e1 * pow(sin(blh.B), 2));

	V = WGS84_a / W;

	dSin1miao = sin(0.0000048481368110185185);

	dUTM_k0 = 0.9996;

	dFalseEasting = 500000;									//东移假定值500Km

	dLocalLatitude = blh.B;									//该点已知的纬度 单位：弧度

	dCenterLongitude = (nUTMZoneNum - 30 - 1) * 6 + 3;				//东半球UTM区域中心经线，单位：度

	dLocalLongitude = blh.L;

	dLocalLongitude = dLocalLongitude * 180 / PI;				//该点已知的经度, 已知数据的弧度转为度

	dDertaNumda = (dLocalLongitude - dCenterLongitude) * 3600;	//单位：秒

	dP = 0.0001*dDertaNumda;

	dn = WGS84_f / (2 - WGS84_f);

	dA1 = WGS84_a * (1 - dn + (5.0 / 4.0)*(pow(dn, 2) - pow(dn, 3)) + (81.0 / 64.0)*(pow(dn, 4) - pow(dn, 5)));

	dB1 = (double)(3.0 / 2.0)*WGS84_a*(dn - pow(dn, 2) + (double)(7.0 / 8.0)*(pow(dn, 3) - pow(dn, 4)) + (double)(55.0 / 64.0)*pow(dn, 5));

	dC1 = (double)(15.0 / 16.0)*WGS84_a*(pow(dn, 2) - pow(dn, 3) + (3.0 / 4.0)*(pow(dn, 4) - pow(dn, 5)));

	dD1 = (double)(35.0 / 48.0)*WGS84_a*(pow(dn, 3) - pow(dn, 4) + (11.0 / 16.0)*pow(dn, 5));

	dE1 = (double)(315.0 / 512.0)*WGS84_a*(pow(dn, 4) - pow(dn, 5));

	dS = dA1 * dLocalLatitude - dB1 * sin(2 * dLocalLatitude) + dC1 * sin(4 * dLocalLatitude) - dD1 * sin(6 * dLocalLatitude) + dE1 * sin(8 * dLocalLatitude);

	dT3 = (V*sin(dLocalLatitude)*pow(cos(dLocalLatitude), 3)*dUTM_k0 / 24.0)*(5 - pow(tan(dLocalLatitude), 2) + 9 * WGS84_e2*pow(cos(dLocalLatitude), 2) + 4 * pow(WGS84_e2, 2)*pow(cos(dLocalLatitude), 4));

	dT4 = (V*sin(dLocalLatitude)*pow(cos(dLocalLatitude), 5)*dUTM_k0 / 720.0)*(61 - 58 * pow(tan(dLocalLatitude), 2) + pow(tan(dLocalLatitude), 4) + 270 * WGS84_e2*pow(cos(dLocalLatitude), 2)
		- 330 * pow(tan(dLocalLatitude), 2)*WGS84_e2*pow(cos(dLocalLatitude), 2) + 445 * pow(WGS84_e2, 2)*pow(cos(dLocalLatitude), 4) + 324 * pow(WGS84_e2, 3)*pow(cos(dLocalLatitude), 6)
		- 680 * pow(tan(dLocalLatitude), 2)*pow(WGS84_e2, 2)*pow(cos(dLocalLatitude), 4) + 88 * pow(WGS84_e2, 4)*pow(cos(dLocalLatitude), 8) - 600 * pow(tan(dLocalLatitude), 2)*pow(WGS84_e2, 3)*pow(cos(dLocalLatitude), 6)
		- 192 * pow(tan(dLocalLatitude), 2)*pow(WGS84_e2, 4)*pow(cos(dLocalLatitude), 8));

	dT8 = (V*pow(cos(dLocalLatitude), 5)*dUTM_k0 / 120)*(5 - 18 * pow(tan(dLocalLatitude), 2) + pow(tan(dLocalLatitude), 4) + 14 * WGS84_e2*pow(cos(dLocalLatitude), 2)
		- 58 * pow(tan(dLocalLatitude), 2)*WGS84_e2*pow(cos(dLocalLatitude), 2) + 13 * pow(WGS84_e2, 2)*pow(cos(dLocalLatitude), 4) + 4 * pow(WGS84_e2, 3)*pow(cos(dLocalLatitude), 6)
		- 64 * pow(tan(dLocalLatitude), 2)*pow(WGS84_e2, 2)*pow(cos(dLocalLatitude), 4) - 24 * pow(tan(dLocalLatitude), 2)*pow(WGS84_e2, 3)*pow(cos(dLocalLatitude), 6));

	dPosN = dS * dUTM_k0 + (V*sin(dLocalLatitude)*cos(dLocalLatitude)*dUTM_k0 / 2.0)*pow(dSin1miao, 2)*pow(dP, 2)*pow(10.0, 8) + dT3 * pow(dSin1miao, 4)*pow(dP, 4)*pow(10.0, 16)
		+ dT4 * pow(dSin1miao, 6)*pow(dP, 6)*pow(10.0, 24);

	dPosE = V * cos(dLocalLatitude)*dUTM_k0*dSin1miao*dP*pow(10.0, 4) + (V*pow(cos(dLocalLatitude), 3)*dUTM_k0 / 6.0)*(1 - pow(tan(dLocalLatitude), 2) + WGS84_e2 * pow(cos(dLocalLatitude), 2))*pow(dSin1miao, 3)*pow(dP, 3)*pow(10.0, 12)
		+ dT8 * pow(dSin1miao, 5)*pow(dP, 5)*pow(10.0, 20);

	utm.X = dPosE + dFalseEasting;
	utm.Y = dPosN;
	utm.Z = blh.H;
	return utm;
}

LidarBLH XYZ2BLH(LidarPt xyz)
{
	LidarBLH blh;

	double L;
	double B;
	double H;
	double B0;							//迭代初值
	double dTempB;
	double N;							//椭球的卯酉圈曲率半径 N=a/W
	double W;
	double dThreshold;
	double Phi;

	double X = xyz.X;
	double Y = xyz.Y;
	double Z = xyz.Z;

	B = 0;
	dThreshold = 0.000000004848136;       //0.0001秒所对应的弧度
	Phi = atan(Z / (sqrt(pow(X, 2) + pow(Y, 2))));

	L = atan(Y / X);					//直接解算经度L
	if (L < 0)
	{
		L = PI + L;
	}

	//迭代解算纬度B
	B0 = atan(Z / (sqrt(pow(X, 2) + pow(Y, 2))));
	do
	{
		W = sqrt(1 - WGS84_e1 * pow(sin(B0), 2));
		B = atan(tan(Phi)*(1 + WGS84_a * WGS84_e1*sin(B0) / (Z*W)));
		dTempB = B0;
		B0 = B;
	} while (abs(B0 - dTempB) > dThreshold);
	B = B0;

	double b1 = B;
	double b2 = atan(tan(Phi)*(1 + WGS84_a * WGS84_e1*sin(B0) / (Z*W)));


	//解算高度H
	W = sqrt(1 - WGS84_e1 * pow(sin(B), 2));
	N = WGS84_a / W;
	H = sqrt(pow(X, 2) + pow(Y, 2) + pow(Z, 2))*cos(Phi) / cos(B) - N;


	blh.L = L;
	blh.B = B;
	blh.H = H;
	return blh;
}

double StatisticLoc(vector<LidarALLData>vAlldata,double &dWinLoc)
{
	double dMaxNum = 0.01;		//距离区间
	double dMinNum = 0;			//距离区间
	int nMaxRange = 0;			//最大值
	double dMaxLoc = 0;			//最大值位置-用来判断地物
	int nMaxWinRange = 0;		//窗口回波最大值
	//double dWinLoc			//窗口回波位置
	int *nNum = new int[50000]();

	for (int i = 0; i < 50000; i++)
	{
		int nNumTemp = 0;					//计数
		for (size_t j = 0; j < 5000; j++)	//时间区间
		{
			double dL = vAlldata[j].nTimeInfo * 64e-12 * C / 2.0;
			if (vAlldata[i].nFlag != 1 && dL > dMinNum&&dL < dMaxNum)
				nNumTemp++;
		}
		nNum[i] = nNumTemp;
		dMaxNum += 0.01;
		dMinNum += 0.01;
	}
	for (int i = 0; i < 50000; i++)
	{
		if (i < 200)
		{
			if (nNum[i] > nMaxWinRange)
			{
				nMaxWinRange = nNum[i];
				dWinLoc = i / 100.0;
			}

		}
		else
		{
			if (nNum[i] > nMaxRange)
			{
				nMaxRange = nNum[i];
				dMaxLoc = i / 100.0;
			}

		}
	}
	delete[]nNum; nNum = NULL;

	//检查重叠效应
	double dUsuDis = 0;
	int nM1_start = 0;
	int nM1_end = 0;
	int nNum_M1 = 0;
	bool bCirM1 = false;
	int nSum = 0;
	if (dMaxLoc < 100)//100
	{
		for (size_t i = 0; i < vAlldata.size(); i++)
		{
			if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 1 && bCirM1 == true)
			{
				nM1_end = (int)i;

				int nn1 = vAlldata[nM1_start].nPaulseNum;
				int nn2 = vAlldata[nM1_end].nPaulseNum;
				int m = 0;
				while (vAlldata[nM1_start + m].nFlag == 1)
				{
					m++;
					nn1 = vAlldata[nM1_start + m].nPaulseNum;
				}
				m = 0;
				while (vAlldata[nM1_end - m].nFlag == 1)
				{
					m++;
					nn2 = vAlldata[nM1_end - m].nPaulseNum;
				}
				nNum_M1 = nn2 - nn1;
				break;
			}
			else if (vAlldata[i].nFlag == 1 && vAlldata[i].nChannel == 1 && bCirM1 == false)
			{
				nM1_start = (int)i;
				bCirM1 = true;
			}
		}
		if (nNum_M1 > 0)
			dUsuDis = C / nNum_M1 * 0.5;
	}
	return dUsuDis;
}





void GaussFilt(double *sData, double *sData_FT, int nLen, int nR, int nSig, double &dMeanError)
{
	for (int i = 0; i < nLen; i++)
	{
		sData_FT[i] = sData[i];
	}
	double *dGaussTemp = new double[nR * 2 - 1];
	memset(dGaussTemp, 1, (nR * 2 - 1) * sizeof(double));
	for (int i = 0; i < nR * 2 - 1; i++)
	{
		dGaussTemp[i] = double(exp(double(-pow(i - nR, 2.0)) / double((2 * pow(nSig, 2.0))))) / double(nSig*sqrt(2 * PI));
	}


	for (int i = nR; i < nLen - nR; i++)
	{
		double dsum = 0.0;
		for (int j = i - nR + 1; j < i + nR - 1; j++)
		{
			dsum = dsum + sData[j] * dGaussTemp[j - (i - nR + 1)];
		}
		sData_FT[i] = dsum;
	}
	delete[] dGaussTemp; dGaussTemp = NULL;

	//计算背景噪声和随机噪声
	int nBackNoise = -10000;
	for (int i = nLen - 50; i < nLen; i++)
	{
		if (sData_FT[i] > nBackNoise)
		{
			nBackNoise = (int)sData_FT[i];
		}
	}

	int nTempSum = 0;
	for (int i = 0; i < nLen; i++)
	{
		nTempSum = nTempSum + (int)pow(sData[i] - sData_FT[i], 2.0);
	}
	double dRandNoise = nTempSum / double(nLen);
	dMeanError = 3 * sqrt(abs(dRandNoise));

	//减去背景噪声后的波形
	for (int i = 0; i < nLen; i++)
	{
		sData_FT[i] = sData_FT[i] - nBackNoise;
	}

}


void GaussDecompose(double *sData_FT, int nLen, int nStart, double dRandNoise, vector<GaussPara> &vGauss)
{
	bool judge = 0;
	vector<double> vPks;
	vector<int> vLocs;
	vector<double> vSigma;
	GaussPara gaussPara;

	do {
		double npks = 0;
		int nlocs = 0;
		double dsigma = 0;

		for (int i = nStart; i < nLen; i++)
		{
			if (sData_FT[i] > npks)
			{
				npks = sData_FT[i];
				nlocs = i;
			}
		}

		if (npks == 0 || nlocs == 0)
		{
			break;
		}

		if (npks > dRandNoise)
		{
			judge = 1;
			int j = 0;
			double *dTempSigLeft = new double[nLen];
			double dMaxLeft = 0;
			double dSigmaLeft = 0;
			for (int i = nStart; i < nlocs - 1; i++)
			{
				if (sData_FT[i - 1]<(npks / 2) && sData_FT[i + 1]>(npks / 2))
				{
					dTempSigLeft[j] = i;
					j++;
				}
			}
			for (int i = 0; i < sizeof(dTempSigLeft); i++)
			{
				if (dMaxLeft < dTempSigLeft[i])
				{
					dMaxLeft = dTempSigLeft[i];
				}
			}
			dSigmaLeft = abs(dMaxLeft - nlocs) / sqrt(2 * log(2));

			j = 0;
			double *dTempSigRight = new double[nLen];
			double dMaxRight = 0;
			double dSigmaRight = 0;
			for (int i = nlocs + 1; i < nLen; i++)
			{
				if (sData_FT[i - 1] > (npks / 2) && sData_FT[i + 1] < (npks / 2))
				{
					dTempSigRight[j] = i;
					j++;
				}
			}
			for (int i = 0; i < sizeof(dTempSigRight); i++)
			{
				if (dMaxRight < dTempSigRight[i])
				{
					dMaxRight = dTempSigRight[i];
				}
			}
			dSigmaRight = abs(dMaxRight - nlocs) / sqrt(2 * log(2));

			if (dSigmaLeft < dSigmaRight)
			{
				dsigma = dSigmaLeft;
			}
			else
			{
				dsigma = dSigmaRight;
			}

			double *Gauss = new double[nLen];
			memset(Gauss, 0, sizeof(double)*nLen);
			for (int i = 0; i < nLen; i++)
			{
				Gauss[i] = double(npks*exp(-pow(i - nlocs, 2.0) / (2 * pow(dsigma, 2.0))));
				sData_FT[i] = sData_FT[i] - Gauss[i];
			}

			vLocs.push_back(nlocs);
			vPks.push_back(npks);
			vSigma.push_back(dsigma);

			if (vLocs.size() > nLen&&vPks.size() > nLen&&vSigma.size() > nLen)
			{
				judge = 0;
			}

			delete[] dTempSigLeft; dTempSigLeft = NULL;
			delete[] dTempSigRight; dTempSigRight = NULL;
			delete[] Gauss; Gauss = NULL;

		}
		else
		{
			judge = 0;
		}

	} while (judge == 1);

	for (unsigned int i = 0; i < vLocs.size(); i++)
	{
		gaussPara.nLocation = vLocs[i];
		gaussPara.nPeak = vPks[i];
		gaussPara.dSigma = vSigma[i];
		vGauss.push_back(gaussPara);
	}
	vLocs.clear();
	vPks.clear();
	vSigma.clear();
}




static int spline(int n, int end1, int end2,
	double slope1, double slope2,
	double x[], double y[],
	double b[], double c[], double d[],
	int *iflag)
{
	int nm1, ib, i, ascend;
	double t;
	nm1 = n - 1;
	*iflag = 0;
	if (n < 2)
	{ /* no possible interpolation */
		*iflag = 1;
		goto LeaveSpline;
	}
	ascend = 1;
	for (i = 1; i < n; ++i) if (x[i] <= x[i - 1]) ascend = 0;
	if (!ascend)
	{
		*iflag = 2;
		goto LeaveSpline;
	}
	if (n >= 3)
	{
		d[0] = x[1] - x[0];
		c[1] = (y[1] - y[0]) / d[0];
		for (i = 1; i < nm1; ++i)
		{
			d[i] = x[i + 1] - x[i];
			b[i] = 2.0 * (d[i - 1] + d[i]);
			c[i + 1] = (y[i + 1] - y[i]) / d[i];
			c[i] = c[i + 1] - c[i];
		}
		/* ---- Default End conditions */
		b[0] = -d[0];
		b[nm1] = -d[n - 2];
		c[0] = 0.0;
		c[nm1] = 0.0;
		if (n != 3)
		{
			c[0] = c[2] / (x[3] - x[1]) - c[1] / (x[2] - x[0]);
			c[nm1] = c[n - 2] / (x[nm1] - x[n - 3]) - c[n - 3] / (x[n - 2] - x[n - 4]);
			c[0] = c[0] * d[0] * d[0] / (x[3] - x[0]);
			c[nm1] = -c[nm1] * d[n - 2] * d[n - 2] / (x[nm1] - x[n - 4]);
		}
		/* Alternative end conditions -- known slopes */
		if (end1 == 1)
		{
			b[0] = 2.0 * (x[1] - x[0]);
			c[0] = (y[1] - y[0]) / (x[1] - x[0]) - slope1;
		}
		if (end2 == 1)
		{
			b[nm1] = 2.0 * (x[nm1] - x[n - 2]);
			c[nm1] = slope2 - (y[nm1] - y[n - 2]) / (x[nm1] - x[n - 2]);
		}
		/* Forward elimination */
		for (i = 1; i < n; ++i)
		{
			t = d[i - 1] / b[i - 1];
			b[i] = b[i] - t * d[i - 1];
			c[i] = c[i] - t * c[i - 1];
		}
		/* Back substitution */
		c[nm1] = c[nm1] / b[nm1];
		for (ib = 0; ib < nm1; ++ib)
		{
			i = n - ib - 2;
			c[i] = (c[i] - d[i] * c[i + 1]) / b[i];
		}
		b[nm1] = (y[nm1] - y[n - 2]) / d[n - 2] + d[n - 2] * (c[n - 2] + 2.0 * c[nm1]);
		for (i = 0; i < nm1; ++i)
		{
			b[i] = (y[i + 1] - y[i]) / d[i] - d[i] * (c[i + 1] + 2.0 * c[i]);
			d[i] = (c[i + 1] - c[i]) / d[i];
			c[i] = 3.0 * c[i];
		}
		c[nm1] = 3.0 * c[nm1];
		d[nm1] = d[n - 2];
	}
	else
	{
		b[0] = (y[1] - y[0]) / (x[1] - x[0]);
		c[0] = 0.0;
		d[0] = 0.0;
		b[1] = b[0];
		c[1] = 0.0;
		d[1] = 0.0;
	}
LeaveSpline:
	return 0;
}


static double seval(int ni, double u,
	int n, double x[], double y[],
	double b[], double c[], double d[],
	int *last)
{
	int i, j, k;
	double w;
	i = *last;
	if (i >= n - 1) i = 0;
	if (i < 0) i = 0;
	if ((x[i] > u) || (x[i + 1] < u))//??
	{
		i = 0;
		j = n;
		do
		{
			k = (i + j) / 2;
			if (u < x[k]) j = k;
			if (u >= x[k]) i = k;
		} while (j > i + 1);
	}
	*last = i;
	w = u - x[i];
	w = y[i] + w * (b[i] + w * (c[i] + w * d[i]));
	return (w);
}

void SPL(int n, double *x, double *y, int ni, double *xi, double *yi)
{
	double *b, *c, *d;
	int iflag = 0, last = 0, i = 0;
	b = new double[sizeof(double)*n];
	c = new double[sizeof(double)*n];
	d = new double[sizeof(double)*n];
	if (!d) { cout<<"no enough memory for b,c,d\n"; }
	else {
		spline(n, 0, 0, 0, 0, x, y, b, c, d, &iflag);
		if (iflag == 0)
			cout << "I got coef b,c,d now\n";
		else
			cout << "x not in order or other error\n";;
		for (i = 0; i < ni; i++) {
				yi[i] = seval(ni, xi[i], n, x, y, b, c, d, &last);
		}

		delete[]b;
		delete[]c;
		delete[]d;
	}
}


void InterpSpline(vector<POS>vPOS, LidarPointCLoudA* &PtA,size_t sVecsize,int nChannel)
{
	int nposlegth = (int)vPOS.size();
	double *dPosTime = new double[nposlegth];
	double *dPosLat0 = new double[nposlegth];
	double *dPosLong0 = new double[nposlegth];
	double *dPosHeight0 = new double[nposlegth];
	double *dPosRoll0 = new double[nposlegth];
	double *dPosPitch0 = new double[nposlegth];
	double *dPosHeading0 = new double[nposlegth];
	double *dPosEasting0 = new double[nposlegth];
	double *dPosNorthig0 = new double[nposlegth];
	for (size_t i = 0; i < vPOS.size(); i++) {
		int nPosHourT = (int)floor(vPOS[i].dTime / 3600.0);
		int nPosHour = nPosHourT % 24;
		int nHour = nPosHourT - nPosHour;
		double dPosTime0 = vPOS[i].dTime - nHour * 3600;
		dPosTime[i] = dPosTime0;

		dPosLat0[i] = vPOS[i].dLat;
		dPosLong0[i] = vPOS[i].dLong;
		dPosHeight0[i] = vPOS[i].dHeight;
		dPosRoll0[i] = vPOS[i].dRoll;
		dPosPitch0[i] = vPOS[i].dPitch;
		dPosHeading0[i] = vPOS[i].dHeading;
		dPosEasting0[i] = vPOS[i].dEasting;
		dPosNorthig0[i] = vPOS[i].dNorthing;
	}

	vector<double>vLidarTime;
	vector<int>vi;
	for (size_t i = 0; i < sVecsize; i++) {
		if (PtA[i].nChannel == nChannel && PtA[i].dAngle > 0 && PtA[i].dSegTime > 0) {
			vLidarTime.push_back(PtA[i].dSegTime);
			vi.push_back((int)i);
		}
	}


	int nlength = (int)vLidarTime.size();
	double *dLidarTime = new double[nlength];
	for (int i = 0; i < nlength; i++) {
		dLidarTime[i] = vLidarTime[i];
	}
	vLidarTime.clear();

	double *dPosLat = new double[nlength];
	double *dPosLong = new double[nlength];
	double *dPosHeight = new double[nlength];
	double *dPosRoll = new double[nlength];
	double *dPosPitch = new double[nlength];
	double *dPosHeading = new double[nlength];
	double *dPosEasting = new double[nlength];
	double *dPosNorthig = new double[nlength];

	SPL(nposlegth, dPosTime, dPosLat0, nlength, dLidarTime, dPosLat);
	SPL(nposlegth, dPosTime, dPosLong0, nlength, dLidarTime, dPosLong);
	SPL(nposlegth, dPosTime, dPosHeight0, nlength, dLidarTime, dPosHeight);
	SPL(nposlegth, dPosTime, dPosRoll0, nlength, dLidarTime, dPosRoll);
	SPL(nposlegth, dPosTime, dPosPitch0, nlength, dLidarTime, dPosPitch);
	SPL(nposlegth, dPosTime, dPosHeading0, nlength, dLidarTime, dPosHeading);
	SPL(nposlegth, dPosTime, dPosEasting0, nlength, dLidarTime, dPosEasting);
	SPL(nposlegth, dPosTime, dPosNorthig0, nlength, dLidarTime, dPosNorthig);

	delete[]dPosTime;
	delete[]dPosLat0;	delete[]dPosLong0;	delete[]dPosHeight0;
	delete[]dPosRoll0;	delete[]dPosPitch0;	delete[]dPosHeading0;
	delete[]dPosEasting0;	delete[]dPosNorthig0;
	delete[]dLidarTime;
	
	for (size_t i = 0; i < nlength; i++) {
		PtA[vi[i]].dLat = dPosLat[i];
		PtA[vi[i]].dLong = dPosLong[i];
		PtA[vi[i]].dHeight = dPosHeight[i];
		PtA[vi[i]].dRoll = dPosRoll[i];
		PtA[vi[i]].dPitch = dPosPitch[i];
		PtA[vi[i]].dHeading = dPosHeading[i];
		PtA[vi[i]].dEasting = dPosEasting[i];
		PtA[vi[i]].dNorthing = dPosNorthig[i];
	}
	delete[]dPosLat;	delete[]dPosLong;	delete[]dPosHeight;
	delete[]dPosRoll;	delete[]dPosPitch;	delete[]dPosHeading;
	delete[]dPosEasting;	delete[]dPosNorthig;
	vi.clear();
}