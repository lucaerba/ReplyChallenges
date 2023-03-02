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

class Point {
public: double x;
    double y;
public:
    Point(double x, double y) : x(x), y(y) {}
};
class Build{
public: Point point;
public: int l, c, id;
public: bool placed = false;
public:
    Build(int l, int c, int id, bool placed, const Point &point )
            : l(l), c(c), id(id), placed(placed), point(point) {}
};

class Antenna{

public: int r, c, id;
public: Point point;

    Antenna(int r, int c, int id, const Point &point) : r(r), c(c), id(id), point(point) {}
};


long long int W, H, N, M, R; //width, height,

bool compareLatency( Build i, Build j) {
    return i.l<j.l;
}

bool compareC (vector <Build> i, vector<Build> j){
    return i.size()>j.size();
}
bool compareR(Antenna i, Antenna j){
    return i.r>j.r;
}

int findMax(int i, int j) {
    if (i>j)
        return i;
    else
        return j;
}


double distance(Point p1, Point p2) {
    double dx = p1.x - p2.x;
    double dy = p1.y - p2.y;
    return sqrt(dx * dx + dy * dy);
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
    ofstream fp_out("/Users/manuelfissore/Documents/reply/III_2/prova.txt", ios::out);

    fp_out << output.size() << "\n";
    for(auto o: output){
        fp_out << o.id << " " << o.point.x << " " << o.point.y << "\n";
    }
}
Build findNearest(vector<Build> b_vec, Point p){
    int d_min=1000000;
    Build ret = Build(0,0,0,-1, Point(0,0));
    for (auto b: b_vec) {
        if (distance(b.point, Point(p.x, p.y)) < d_min)
            ret=b;
    }
    return ret;
}

void coverage(Antenna a, vector<Build> c) {
    for (auto b:c) {
        if (distance(a.point, b.point)<a.r)
            builds.at(b.id).placed=true;
    }
}

// Funzione per dividere un insieme di punti in cluster di raggio epsilon costante
vector<vector<Build>> clusterPoints(vector<Build>& buildings, double epsilon) {
    // Numero di punti totali
    int n = buildings.size();

    // Array per tenere traccia di quali punti sono stati visitati
    vector<bool> visited(n, false);

    // Vettore di cluster di punti
    vector<vector<Build>> clusters;

    // Iteriamo su tutti i punti non ancora visitati
    for (int i = 0; i < n; i++) {
        if (!visited[i]) {
            // Aggiungiamo un nuovo cluster
            clusters.push_back(vector<Build>());

            // Aggiungiamo il primo punto al nuovo cluster
            clusters.back().push_back(buildings[i]);
            visited[i] = true;

            // Iteriamo su tutti i punti non ancora visitati
            for (int j = i + 1; j < n; j++) {
                if (!visited[j]) {
                    // Calcoliamo la distanza tra i punti
                    double d = distance(buildings[i].point, buildings[j].point);

                    // Se la distanza è minore o uguale a epsilon, aggiungiamo il punto al cluster
                    if (d <= epsilon) {
                        clusters.back().push_back(buildings[j]);
                        visited[j] = true;
                    }
                }
            }
        }
    }

    return clusters;
}



void findBestFromScore() {
    vector<vector<Build>> clusters;
    vector<Build> c_max;
    Point min = Point(0, 0);
    Point max = Point(0, 0);
    Point avg = Point(0, 0);
    Build best = Build(0, 0, -1, false, Point(0, 0));
    int pos, i = 0, d_min;
    int dist, dist_best, p_old, p_new;

    clusters = clusterPoints(builds, (double) 25); //da modificare
    sort(clusters.begin(), clusters.end(), compareC);
    sort(antennas.begin(), antennas.end(), compareR);

    for (auto c: clusters) {
        i = 0;
        min = Point(1000000, 1000000);
        max = Point(0, 0);
        avg = Point(1000000, 1000000);
        for (auto b: c) {
            if (b.point.x < min.x)
                min.x = (int) b.point.x;
            if (b.point.x > max.x)
                max.x = (int) b.point.x;
            if (b.point.y < min.y)
                min.y = (int) b.point.y;
            if (b.point.y > max.y)
                max.y = (int) b.point.y;
        }
        avg.x = (max.x - min.x) / 2;
        avg.y = (max.y - min.y) / 2;
        for (auto a: antennas) {
            if (a.point.x == 0 && a.point.y == 0 && i < 3) {
                best = Build(0, 0, -1, false, Point(0, 0));;
                for (auto b:c) {
                    if (!b.placed) {
                        if (b.point.x > (avg.x / 2) && b.point.x < (avg.x / 2 + avg.x) && b.point.y > (avg.y / 2) &&
                            b.point.y < (avg.y / 2 + avg.y)) {
                            if (best.id < 0)
                                best = b;
                            dist_best = (int) distance(a.point, best.point);
                            dist = (int) distance(a.point, b.point);
                            p_old = a.c * best.c - dist_best * best.l;
                            p_new = a.c * b.c - dist * b.l;

                            if (p_new > p_old)
                                best = b;
                        }
                    }

                    if (best.id >= 0) {
                        builds.at(best.id).placed = true;
                        a.point = best.point;
                        output.push_back(a);
                        coverage(a, c);
                        i++;
                    }

                }
            }
        }
    }
}
/*
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
            builds.at(best).placed = true;
            a.x = b.x;
            a.y = b.y;
            output.push_back(a);
        }
    }
}
*/
void readFile(){
    ifstream fp_in("/Users/manuelfissore/Documents/reply/III_2/input4.in", ios::in);
    int x,y,l,c,r;

    if(fp_in.is_open()){
        fp_in >> W >> H;
        fp_in >> N >> M >> R;

        for (int i = 0; i < N; ++i) {
            fp_in >> x >> y >> l >> c;
            builds.push_back(Build(l, c, i, false, Point(x, y)));
        }
        for (int i = 0; i < M; ++i) {
            fp_in >> r >> c;
            antennas.push_back(Antenna(r,c,i, Point(0,0)));
        }
    }


#if LOCAL
    cout << W << " " << H << "\n";
    cout << builds.at(0).point.y;
#endif
}
