//
// Created by lucaerba on 3/1/23.
//


#include "libraries.h"
#define LOCAL 1

using namespace std;

void readFile();

long long int W, H, N, M, R; //width, height,

class Build{
    int x,y;
    int l, c;
};

class Antenna{
    int r, c;
};

int main(int argc, char* argv[]) {
    readFile();
    return 0;
}

void readFile(){
    ifstream fp_in("input.txt", ios::in);
    fp_in >> W >> H;
    fp_in >> N >> M >> R;
#if LOCAL
    cout << W << " " << H;
#endif
}
