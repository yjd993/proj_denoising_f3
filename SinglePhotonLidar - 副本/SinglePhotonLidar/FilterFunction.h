#pragma once

#include "Named.h"
#include "Function.h"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <map>
#include <queue>
#include <set>
#include <vector>

// normal filter
#define PULSE_NUM_INT 250				//Pulse Control
#define GLASS_FILTER_THRESHOLD 3000		//Time Info (3000-96m)

// mDBSCAN
#define MEAN_DIST_TOP_K_PERCENT 0.2
#define MIN_PTS 16
#define MIN_DIST_THRESHOLD 10.0
#define MARKER_CLUSTER_K 1



struct DataNeighbour {
	LidarALLData data;
	std::vector<int> neighbours;
};


int getGroup(vector<LidarALLData>&vAlldata, vector<GroupItem>&group, int start);
GroupStats statsGroup(vector<GroupItem> &group);
bool compareItemByTimeInfo(const GroupItem &a, const GroupItem &b);
bool compareItemByIndex(const GroupItem &a, const GroupItem &b);
bool compareStatsByMean(const GroupStats &a, const GroupStats &b);

int filter_period(vector<LidarALLData>&vAlldata, vector<LidarALLData>&filteredData);
int filter(vector<LidarALLData>&vAlldata, vector<LidarALLData>&filteredData);

void filter_mDBSCAN(std::vector<LidarALLData>&vAlldata, std::vector<LidarALLData>&filteredData);
int getGroupAndMarker(std::vector<LidarALLData>&vAlldata, std::vector<GroupItem>&group, std::vector<GroupItem> &marker, int start);
void getNeighbours(std::vector<GroupItem> &group, std::map<int, DataNeighbour> &neighbours, std::set<int> &core_set);
std::set<int> initUnvisitedSet(std::vector<GroupItem> &group);



vector<LidarALLData> HistogramExFilter(vector<LidarALLData>vAlldata, int nInterval);
vector<LidarALLData>HistogramFilter(vector<LidarALLData>vAlldata, int nValue);
