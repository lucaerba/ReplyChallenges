//
// Created by lucaerba on 3/1/23.
//


#include "libraries.h"
#define LOCAL 1

using namespace std;

void readFile();
void findBest();
void printOut();
void findBestFromScore();

class Build{

public: int x,y;
public: int l, c, id;
public: bool placed = 0;
public:
    Build(int x, int y, int l, int c, int id) : x(x), y(y), l(l), c(c), id(id) {}

};

class Antenna{

public: int r, c, id, x, y;

public:
    Antenna(int r, int c, int id) : r(r), c(c), id(id) {}
};


long long int W, H, N, M, R; //width, height,
bool compareLatency( Build i, Build j) {
    return i.l<j.l;
}
vector<Build> builds;
vector<Antenna> antennas;
vector<Antenna> output;

int main(int argc, char* argv[]) {
    readFile();
    findBestFromScore();
    printOut();
    return 0;
}

void printOut() {
    ofstream fp_out("/home/lucaerba/CLionProjects/ReplyChallenges1/2022/output.txt", ios::out);

    fp_out << output.size() << "\n";
    for(auto o: output){
        fp_out << o.id << " " << o.x << " " << o.y << "\n";
    }
}

void findBestFromScore(){
    Build best = Build(0,0,0,0,-1);
    int dist, dist_best;
    int p_old, p_new;
    vector<Build> builds_sort = vector<Build> (builds);

    sort(builds_sort.begin(), builds_sort.end(), compareLatency);

    for(auto a:antennas){
        best = Build(0,0,0,0,-1);
        for(auto b: builds_sort){
            if(builds.at(b.id).placed)
                continue;

            if(b.id == 267){
                cout << "WTF";
                cout << "diocan";
            }

            if(best.id<0) best = b;

            dist_best = abs(a.x-best.x)+abs(a.y-best.y);
            dist = abs(a.x-b.x)+abs(a.y-b.y);
            p_old = a.c * best.c - dist_best * best.l;
            p_new = a.c * b.c - dist * b.l;

            if(p_new > p_old)
                best = b;
        }
        if(best.id >= 0){
            builds.at(best.id).placed = 1;
            a.x = best.x;
            a.y = best.y;
            output.push_back(a);
        }
    }
}

void findBest() {
    int best;
    for(auto a:antennas){
        best = -1;
        for(auto b: builds){
            if(b.placed)
                continue;

            if(best<0) best = b.id;

            if((a.c * b.c) > (a.c * builds.at(best).c))
                best = b.id;
        }
        if(best>=0){
            Build b = builds.at(best);
            builds.at(best).placed = 1;
            a.x = b.x;
            a.y = b.y;
            output.push_back(a);
        }
    }
}

void readFile(){
    ifstream fp_in("/home/lucaerba/CLionProjects/ReplyChallenges/2022/input4.in", ios::in);
    int x,y,l,c,r;

    if(fp_in.is_open()){
        fp_in >> W >> H;
        fp_in >> N >> M >> R;

        for (int i = 0; i < N; ++i) {
            fp_in >> x >> y >> l >> c;
            builds.push_back(Build(x,y,l,c, i));
        }
        for (int i = 0; i < M; ++i) {
            fp_in >> r >> c;
            antennas.push_back(Antenna(r,c,i));
        }
    }


#if LOCAL
    cout << W << " " << H << "\n";
    cout << builds.at(0).y;
#endif
}
