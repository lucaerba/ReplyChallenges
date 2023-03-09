#include "libraries.h"

using namespace std;

class Point{
public: int x, y;
public:
    Point(int x, int y) : x(x), y(y) {}
};
class Warmhole: public Point{
public: int id, max_id, max_pt;
public:
    Warmhole(int x, int y, int id) : Point(x, y), id(id) {}
};
class Valuable: public Point{
public: int id, value;
public:
    Valuable(int x, int y, int id, int value) : Point(x, y), id(id), value(value) {}
};
class Snake{
public: int id;
public: Point start;
public: string path;

public:
    Snake(int id, string path) : id(id), path(path), start(Point(-1,-1)) {}
};

int C, R, S;
vector<Snake> snakes;
vector<Valuable> relevance;
vector<Warmhole> wormholes;

Point** matr;




int main(const int argc, const char * argv[]) {
    cout << "prova";
    return 0;
}

void readInput() {
    ifstream file;
    file.open("input.txt");
    file >> C >> R >> S;
    matr = new Point*[C*R];
    for (int i = 0; i < S; i++) {
        int temp;
        file >> temp;
        snakes.push_back(Snake(i, ""));
    }
    int count = 0;
    for (int i = 0; i < C; i++) {
        for (int j = 0; j < R; j++) {
            int temp;
            file >> temp;
           
            if (temp == '*') {
                Warmhole wh = Warmhole(i, j, count++ );
                wormholes.push_back(wh);
                matr[i*C+j] = &wh;
            } else {
                Valuable r = Valuable(i, j, count++, temp);
                relevance.push_back(r);
                matr[i*C+j] = &r;
            }
        }
    }
    file.close();
}