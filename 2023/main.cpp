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
};


int main(const int argc, const char * argv[]) {
    //TODO: enjoy
    return 0;
}

