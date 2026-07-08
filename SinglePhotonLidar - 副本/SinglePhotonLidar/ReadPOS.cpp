// ReadPOS.cpp : This file contains the 'main' function. Program execution begins and ends there.
//

#include "pch.h"
#include <iostream>
#include <fstream>
#include <iostream>
#include <sstream>
#include <vector>

using namespace std;

struct POS
{
	int id;
	int event;
	double time;
	double easting;
	double northing;
	double ellipsoid_height;
	double omega;
	double phi;
	double kappa;
	double lat;
	double lon;
};

vector<POS> ReadPOS(string pos_path);

int main()
{
	std::cout << "Hello World!\n";

	vector<POS> pos_data = ReadPOS("C:\\data\\eo_Mission 1.txt");

	if (pos_data.size() > 2) {
		POS p0 = pos_data[0];
		POS p1 = pos_data[1];
		cout << endl;
	}

}

vector<POS> ReadPOS(string pos_path)
{
	vector<POS> pos_data;
	ifstream pos_file_stream(pos_path);
	stringstream pos_buffer;
	pos_buffer << pos_file_stream.rdbuf();
	string start_marker = " (position in Meters, orientation in Degrees, lat, long in Deg) ";
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
			rs >> pos.event >> pos.time >> pos.easting >> pos.northing >> pos.ellipsoid_height
				>> pos.omega >> pos.phi >> pos.kappa >> pos.lat >> pos.lon;
			pos_data.push_back(pos);
		}
	}
	return pos_data;
}

// Run program: Ctrl + F5 or Debug > Start Without Debugging menu
// Debug program: F5 or Debug > Start Debugging menu

// Tips for Getting Started: 
//   1. Use the Solution Explorer window to add/manage files
//   2. Use the Team Explorer window to connect to source control
//   3. Use the Output window to see build output and other messages
//   4. Use the Error List window to view errors
//   5. Go to Project > Add New Item to create new code files, or Project > Add Existing Item to add existing code files to the project
//   6. In the future, to open this project again, go to File > Open > Project and select the .sln file
