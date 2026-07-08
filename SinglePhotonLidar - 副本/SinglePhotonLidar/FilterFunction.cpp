#include "FilterFunction.h"
using namespace std;

bool compareItemByTimeInfo(const GroupItem &a, const GroupItem &b) {
	return a.data.nTimeInfo < b.data.nTimeInfo;
}

bool compareItemByIndex(const GroupItem &a, const GroupItem &b) {
	return a.index < b.index;
}

bool compareStatsByMean(const GroupStats &a, const GroupStats &b) {
	return a.mean < b.mean;
}
int HALF_K_NEIGHBOUR = 20;
double N_STDEV = 1.0;
// filter_period
int PERIOD_GROUP_COUNT = 50000 / PULSE_NUM_INT;
double MIN_MEAN_PERCENT = 0.04;//0.20

int filter(vector<LidarALLData>&vAlldata, vector<LidarALLData>&filteredData) {
	int i = 0;
	while (true) {
		if (i >= vAlldata.size()) {
			break;
		}
		vector<GroupItem> group;
		i = getGroup(vAlldata, group, i);
		if (group.size() == 0) {
			continue;
		}
		GroupStats stats = statsGroup(group);
		sort(group.begin(), group.end(), compareItemByIndex);
		for (int j = 0; j < group.size(); j++) {
			// keep marker
			if (group[j].data.nFlag != 1) {
				if (group[j].kmean_dist > stats.mean + stats.stdev * N_STDEV) {
					continue;
				}
			}
			//if (group[j].kmean_dist < stats.mean - stats.stdev * N_STDEV) {
			//  continue;
			//}
			vAlldata[group[j].index].nClass = 1;
			filteredData.push_back(group[j].data);
		}
	}
	return 0;
}

int filter_period(vector<LidarALLData>&vAlldata, vector<LidarALLData>&filteredData) {
	int i = 0;
	while (true) {
		if (i >= vAlldata.size()) {
			break;
		}
		vector<vector<GroupItem>> group_list;
		vector<GroupStats> stats_list;
		for (int p = 0; p < PERIOD_GROUP_COUNT; p++) {
			if (i >= vAlldata.size()) {
				break;
			}
			vector<GroupItem> group;
			i = getGroup(vAlldata, group, i);
			if (group.size() == 0) {
				continue;
			}
			GroupStats stats = statsGroup(group);
			group_list.push_back(group);
			stats_list.push_back(stats);
		}
		if (group_list.size() == 0) {
			continue;
		}
		sort(stats_list.begin(), stats_list.end(), compareStatsByMean);
		int pstats_index = (stats_list.size() - 1)*MIN_MEAN_PERCENT;
		GroupStats period_stats = stats_list[pstats_index];
		for (int p = 0; p < group_list.size(); p++) {
			vector<GroupItem> group = group_list[p];
			sort(group.begin(), group.end(), compareItemByIndex);
			for (int j = 0; j < group.size(); j++) {
				// keep marker
				if (group[j].data.nFlag != 1) {
					if (group[j].kmean_dist > period_stats.mean + period_stats.stdev * N_STDEV) {
						continue;
					}
				}
				//if (group[j].kmean_dist < stats.mean - stats.stdev * N_STDEV) {
				//  continue;
				//}
				vAlldata[group[j].index].nClass = 1;
				filteredData.push_back(group[j].data);
			}
		}
	}
	return 0;
}


int getGroup(vector<LidarALLData>&vAlldata, vector<GroupItem>&group, int start) {
	int i = start;
	int startPulseNum = 0;
	for (; true; i++) {
		if (i >= vAlldata.size()) {
			break;
		}
		if (startPulseNum == 0) {
			startPulseNum = vAlldata[i].nPaulseNum;
		}
		if (vAlldata[i].nPaulseNum > startPulseNum + PULSE_NUM_INT) {
			break;
		}
		// filter glass
		//if (vAlldata[i].nTimeInfo <= 105) {
		if (vAlldata[i].nTimeInfo <= GLASS_FILTER_THRESHOLD) {
			// keep marker
			if (vAlldata[i].nFlag != 1) {
				continue;
			}
		}
		GroupItem item;
		item.data = vAlldata[i];
		item.index = i;
		item.kmean_dist = 0;
		group.push_back(item);
	}
	return i;
}
GroupStats statsGroup(vector<GroupItem> &group) {
	int half_k = HALF_K_NEIGHBOUR;
	int k = half_k * 2;
	if (k > group.size()) {
		k = group.size();
	}
	sort(group.begin(), group.end(), compareItemByTimeInfo);
	// TODO NOT STATS MARKER DATA
	for (int i = 0; i < group.size(); i++) {
		int start;
		if (i - half_k < 0)
		{
			start = 0;
		}
		else if (i + half_k > group.size() - 1)
		{
			start = group.size() - k - 1;
		}
		else
		{
			start = i - half_k;
		}
		uint16_t i_nTimeInfo = group[i].data.nTimeInfo;
		double sum_dist = 0.0;
		for (int j = 0; j < k + 1; j++) {
			sum_dist += abs(group[start + j].data.nTimeInfo - i_nTimeInfo);
		}
		group[i].kmean_dist = sum_dist / k;
	}
	/*
	double group_dist_sum = 0.0;
	for (int i = 0; i < group.size(); i++) {
		group_dist_sum += group[i].kmean_dist;
	}
	double group_dist_mean = group_dist_sum / group.size();
	double group_dist_accum = 0.0;
	for (int i = 0; i < group.size(); i++) {
		double v = (group[i].kmean_dist - group_dist_mean)*(group[i].kmean_dist - group_dist_mean);
		group_dist_accum += v;
	}
	double stdev = sqrt(group_dist_accum / group.size());
	*/
	vector<double> kmean_dist_list;
	for (int i = 0; i < group.size(); i++) {
		kmean_dist_list.push_back(group[i].kmean_dist);
	}
	sort(kmean_dist_list.begin(), kmean_dist_list.end());
	int kdl_index = (kmean_dist_list.size() - 1)*MIN_MEAN_PERCENT;
	GroupStats stats;
	stats.mean = kmean_dist_list[kdl_index];
	stats.stdev = stats.mean * 0.2;
	return stats;
}

void filter_mDBSCAN(std::vector<LidarALLData>&vAlldata, std::vector<LidarALLData>&filteredData) {
	int i = 0;
	while (true) {
		if (i >= vAlldata.size()) {
			break;
		}
		std::vector<GroupItem> group;
		std::vector<GroupItem> marker;
		i = getGroupAndMarker(vAlldata, group, marker, i);
		if (group.size() == 0) {
			continue;
		}

		for (int m = 0; m < marker.size(); m++) {
			int index = marker[m].index;
			filteredData.push_back(vAlldata[index]);
			vAlldata[index].nClass = MARKER_CLUSTER_K;
		}

		std::map<int, DataNeighbour> neighbours;
		std::set<int> core_set;
		getNeighbours(group, neighbours, core_set);
		std::set<int> unvisited_core_set = core_set;
		std::set<int> unvisited_set = initUnvisitedSet(group);
		int cluster_k = 10;
		while (unvisited_core_set.size() > 0) {
			std::queue<int> q;
			int index = *(unvisited_core_set.begin());
			filteredData.push_back(vAlldata[index]);
			vAlldata[index].nClass = cluster_k;
			q.push(index);
			unvisited_set.erase(index);
			if (index % 100 == 0) {
				std::cout << "filtered point i=" << index << " nTimeInfo=" << vAlldata[index].nTimeInfo << std::endl;
			}
			while (!q.empty()) {
				int data_index = q.front();
				q.pop();
				if (core_set.find(data_index) == core_set.end()) {
					continue;
				}
				unvisited_core_set.erase(data_index);
				std::vector<int> selected_neighbours = neighbours[data_index].neighbours;
				for (auto iter = selected_neighbours.begin(); iter != selected_neighbours.end(); iter++) {
					int neighbour_index = *iter;
					if (unvisited_set.find(neighbour_index) == unvisited_set.end()) {
						continue;
					}
					filteredData.push_back(vAlldata[neighbour_index]);
					vAlldata[neighbour_index].nClass = cluster_k;
					q.push(neighbour_index);
					unvisited_set.erase(neighbour_index);
				}
			}
			cluster_k += 1;
		}
	}
}

int getGroupAndMarker(std::vector<LidarALLData>&vAlldata, std::vector<GroupItem>&group, std::vector<GroupItem> &marker, int start) {
	int i = start;
	uint32_t startPulseNum = 0;
	for (; true; i++) {
		if (i >= vAlldata.size()) {
			break;
		}
		if (startPulseNum == 0) {
			startPulseNum = vAlldata[i].nPaulseNum;
		}
		if (vAlldata[i].nPaulseNum > startPulseNum + PULSE_NUM_INT) {
			break;
		}
		// keep marker
		if (vAlldata[i].nFlag == 1) {
			GroupItem item;
			item.data = vAlldata[i];
			item.index = i;
			item.kmean_dist = 0;
			marker.push_back(item);
			continue;
		}
		// filter glass
		if (vAlldata[i].nTimeInfo <= GLASS_FILTER_THRESHOLD) {
			continue;
		}
		GroupItem item;
		item.data = vAlldata[i];
		item.index = i;
		item.kmean_dist = 0;
		group.push_back(item);
	}
	return i;
}


void getNeighbours(std::vector<GroupItem> &group, std::map<int, DataNeighbour> &neighbours, std::set<int> &core_set) {
	// estimate params
	int min_pts = MIN_PTS;
	sort(group.begin(), group.end(), compareItemByTimeInfo);
	std::vector<double> windows_dist_mean;
	for (int i = 0; i + min_pts - 1 < group.size(); i += min_pts) {
		double sum = 0;
		for (int j = i; j < i + min_pts; j++) {
			sum += group[j].data.nTimeInfo;
		}
		if (sum == 0) {
			continue;
		}
		double mean = sum / min_pts;
		double dist_sum = 0;
		for (int j = i; j < i + min_pts; j++) {
			dist_sum += abs(group[j].data.nTimeInfo - mean);
		}
		double dist_mean = dist_sum / min_pts;
		windows_dist_mean.push_back(dist_mean);
	}
	sort(windows_dist_mean.begin(), windows_dist_mean.end());
	int selected_dist_mean_index = 0;
	if (windows_dist_mean.size() > 0) {
		selected_dist_mean_index = int((windows_dist_mean.size() - 1) * MEAN_DIST_TOP_K_PERCENT);
	}
	double distance_threshold = windows_dist_mean[selected_dist_mean_index];
	distance_threshold = distance_threshold / min_pts * 4;
	if (distance_threshold < MIN_DIST_THRESHOLD) {
		distance_threshold = MIN_DIST_THRESHOLD;
	}
	if ((*group.begin()).index % 100 == 0) {
		std::cout << "estimate params" << " i=" << (*group.begin()).index << " distance_threshold=" << distance_threshold
			<< " selected_dist_mean_index=" << selected_dist_mean_index << std::endl;
	}

	for (int i = 0; i < group.size(); i++) {
		DataNeighbour data_neighbour;
		data_neighbour.data = group[i].data;
		for (int j = i - 1; j >= 0; j--) {
			int dist = abs(group[j].data.nTimeInfo - group[i].data.nTimeInfo);
			if (dist > distance_threshold) {
				break;
			}
			data_neighbour.neighbours.push_back(group[j].index);
		}
		for (int k = i + 1; k < group.size(); k++) {
			int dist = abs(group[k].data.nTimeInfo - group[i].data.nTimeInfo);
			if (dist > distance_threshold) {
				break;
			}
			data_neighbour.neighbours.push_back(group[k].index);
		}
		neighbours[group[i].index] = data_neighbour;
		if (data_neighbour.neighbours.size() >= min_pts) {
			core_set.insert(group[i].index);
		}
	}
}

std::set<int> initUnvisitedSet(std::vector<GroupItem> &group) {
	std::set<int> unvisited_set;
	for (int i = 0; i < group.size(); i++) {
		unvisited_set.insert(group[i].index);
	}
	return unvisited_set;
}

vector<LidarALLData> HistogramExFilter(vector<LidarALLData>vAlldata, int nInterval)
{
	vector<LidarALLData>vFilter;

	int nMaxNum = 1;
	int nMinNum = 0;
	int *nNum = new int[500];
	int nMaxRange = 0;
	int nMaxLoc = 0;
	for (int i = 0; i < 500; i++)
	{
		int nNumTemp = 0;
		for (size_t j = 0; j < vAlldata.size(); j++)
		{
			double dL = vAlldata[j].nTimeInfo*0.000000000001 * 64 * C / 2.0;
			if (vAlldata[i].nFlag != 1 && dL > nMinNum&&dL < nMaxNum)
				nNumTemp++;
		}
		nNum[i] = nNumTemp;
		nMaxNum++;
		nMinNum++;
	}
	for (int i = 10; i < 500; i++)
	{
		if (nNum[i] > nMaxRange)
		{
			nMaxRange = nNum[i];
			nMaxLoc = i;
		}
	}

	for (size_t i = 0; i < vAlldata.size(); i++)
	{
		double dL = vAlldata[i].nTimeInfo*0.000000000001 * 64 * C / 2.0;
		if (vAlldata[i].nFlag == 1 || (dL > nMaxLoc - nInterval && dL < nMaxLoc + nInterval+1))
		{
			vFilter.push_back(vAlldata[i]);
		}
	}
	delete[]nNum; nNum = NULL;

	return vFilter;
}

vector<LidarALLData>HistogramFilter(vector<LidarALLData>vAlldata,int nValue)
{
	vector<LidarALLData>vFilterData;
	////////////////////////////////////////////////////
	int nMaxNum = 1;						//1m分辨率上限
	int nMinNum = 0;						//1m分辨率下限
	int nPaulseSatart = 0;					//时间窗口起始 光子个数起始位置/脉冲个数
	int nPaulseEnd = 1000;					//时间窗口终止 光子个数终止位置/脉冲个数
	int nStart = 0;							//斜距窗口起始
	int nEnd = 0;							//斜距窗口终止
	bool bValldata = false;					//数据size控制
	double *dNum = new double[500]();		//概率密度统计
	StatsMax *GroupMax = new StatsMax[10]();
	double dLmax = 0;

	while (bValldata == false)
	{
		memset(dNum, 0, sizeof(double) * 500);
		memset(GroupMax, 0, sizeof(StatsMax) * 10);
		nMaxNum = 1;
		nMinNum = 0;

		for (int i = 0; i < 500; i++)
		{
			int nNumTemp = 0;
			int nMark = 0;
			for (int j = nPaulseSatart; j < nPaulseEnd; j++)
			{
				double dLtimeinfo = vAlldata[j].nTimeInfo*64e-12 * C / 2.0;
				if (vAlldata[j].nFlag != 1 && dLtimeinfo > nMinNum && dLtimeinfo < nMaxNum)
					nNumTemp++;
				else if (vAlldata[j].nFlag == 0)
					nMark++;
				if (dLmax < dLtimeinfo)
					dLmax = dLtimeinfo;
			}
			dNum[i] = (double)nNumTemp / nMark;
			nMaxNum += 1;
			nMinNum += 1;
			//cout << i<<" "<< setprecision(6)<<dNum[i] << endl;
		}

		double dNoise = 0.0;
		for (int i = dLmax; i < dLmax-10; i++)
		{
			if (dNum[i] > dNoise)
				dNoise = dNum[i];
		}
		dNoise = nValue * dNoise;
		//cout << dNoise << endl;

		double dMaxTemp = 0.0;
		int nMaxLocTemp = 0;
		for (int i = 10; i < 500; i++)
		{
			if (dNum[i] > dMaxTemp)
			{
				dMaxTemp = dNum[i];
				nMaxLocTemp = i;
			}
		}
		nStart = nMaxLocTemp - 10;
		nEnd = nMaxLocTemp + 10;
		if (nEnd > 300)
			nEnd = 300;


		for (int m = 0; m < 10; m++)
		{
			for (int i = nStart; i < nEnd; i++)
			{
				if (dNum[i] > GroupMax[m].dMaxRange && m == 0)
				{
					GroupMax[m].dMaxRange = dNum[i];
					GroupMax[m].nMaxLoc = i;
				}
				else if (dNum[i] > GroupMax[m].dMaxRange && dNum[i] < GroupMax[m - 1].dMaxRange)
				{
					GroupMax[m].dMaxRange = dNum[i];
					GroupMax[m].nMaxLoc = i;
				}
			}
			//cout << GroupMax[m].nMaxLoc << " " << GroupMax[m].dMaxRange << " " << dNum[GroupMax[m].nMaxLoc] << endl;
			for (int i = nPaulseSatart; i < nPaulseEnd; i++)
			{
				double dLtimeinfo = vAlldata[i].nTimeInfo*64e-12 * C / 2.0;
				if (vAlldata[i].nFlag == 1 || (dLtimeinfo > GroupMax[m].nMaxLoc - 1 && dLtimeinfo < GroupMax[m].nMaxLoc && GroupMax[m].dMaxRange > dNoise&&dLtimeinfo>5))
				{
					vAlldata[i].nClass = 1;
				}
			}
		}
		//cout << endl;

		nPaulseSatart = nPaulseEnd;
		nPaulseEnd += 1000;
		if (nPaulseEnd > (int)vAlldata.size())
			nPaulseEnd = (int)vAlldata.size();
		if (nPaulseSatart == (int)vAlldata.size())
			bValldata = true;

	}

	for (size_t i = 0; i < vAlldata.size(); i++)
	{
		if (vAlldata[i].nClass == 1)
		{
			LidarALLData tempdata;
			tempdata = vAlldata[i];
			vFilterData.push_back(tempdata);
		}
	}
	delete[]dNum; dNum = NULL;
	delete[]GroupMax; GroupMax = NULL;

	return vFilterData;
}