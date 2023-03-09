#include "libraries.h"
#define INPUT "./2023/00-example.txt"
using namespace std;

template<typename Base, typename T>
inline bool instanceof(const T *ptr) {
    return dynamic_cast<const Base*>(ptr) != nullptr;
}

class Point{
public: int x, y;
public:
    Point(int x, int y) : x(x), y(y) {}

    Point() {}
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
public: int id, l;
public: Point start;
public: string path;

public:
    Snake(int id, string path, int l) : id(id), path(path), start(Point(-1,-1)), l(l) {}
};

int C, R, S;
char dir;
vector<Snake> snakes;
vector<Valuable> relevance;
vector<Warmhole> wormholes;

Point** matr;


void findSolution();
void optimizeSolution();
void readInput();
void printOut();
Valuable findBest();

bool compareValue(Valuable v1, Valuable v2){
    return v1.value > v2.value;
}
int main(const int argc, const char * argv[]) {
    readInput();
    std::sort(relevance.begin(), relevance.end(), compareValue);
    findSolution();
    optimizeSolution();
    printOut();
    return 0;
}

void readInput() {
    ifstream file;
    file.open(INPUT);
    file >> C >> R >> S;
    matr = new Point*[R];
    for(int i=0; i<R; i++) matr[i] = new Point[C];

    for (int i = 0; i < S; i++) {
        int temp;
        file >> temp;
        snakes.push_back(Snake(i, "", temp));
    }
    int count = 0;
    for (int i = 0; i < C; i++) {
        for (int j = 0; j < R; j++) {
            char temp;
            file >> temp;
           
            if (temp == '*') {
                Warmhole wh = Warmhole(i, j, count++ );
                wormholes.push_back(wh);
                matr[i*C+j] = &wh;
            } else {
                Valuable r = Valuable(i, j, count++, temp-48);
                relevance.push_back(r);
                matr[i*C+j] = &r;
            }
        }
    }
    file.close();
}
Valuable findBest(Point v){
    Point *ret;
    char flag;
    int score, maxscore;
    if(v.y<R-1)
        ret=matr[v.x+1+C*v.y];
    else
        ret=matr[C*v.y];
    flag=R;
    if(instanceof<Valuable>(ret))
        score= ((Valuable*) ret)->value;
    //else
    maxscore=score;
    if(v.x<C-1)
        ret=matr[v.x+C*(v.y+1)];
    else
        ret=matr[v.x+C*(v.y+1)];
}

void findSolution(){
    for(auto s: snakes){
        Valuable v = relevance.at(0);
        relevance.erase(relevance.begin());
        int l = s.l-1;
        while(l > 0){

        }
    }
}
void optimizeSolution(){

}

void printOut(){
    ofstream fp_out("./output.txt", ios::out);
    for(auto s:snakes) {
        fp_out << s.start.x << " " << s.start.y << " ";
        for (auto v: s.path)
            fp_out << v << " ";
        fp_out << "\n";
    }
}

