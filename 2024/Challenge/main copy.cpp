#include <iostream>
#include <vector>
#include <fstream>
#define DEBUG 1

#define INPUT 0
using namespace std;
// input vars

//input files

ifstream in("00-trailer.txt");
//ifstream in("01-comedy.txt");
//ifstream in("02-sentimental.txt");
//ifstream in("03-adventure.txt");
//ifstream in("04-drama.txt");
//ifstream in("05-horror.txt");

//#define LR, UD, LU, LD, UR, DR
#define LR 0
#define UD 1
#define LU 2
#define LD 3
#define UR 4
#define DR 5



int W, H, Gn, Sm, Tl;
struct Tile {
    string id;
    vector<int> paths;
};

struct SilverPoint {
    int val;
    pair<int, int> coord;
};

struct GoldenPoint {
    pair<int, int> coord;
};

struct SolutionLine {
    string id;
    vector<pair<int, int>> coords;
};


//create the data structure for the tiles, each has an ID and a vector of the possible paths
/*Tile 3:
From left to right (*)
Tile 5:
From down to right (*)
Tile 6:
From left to down (*)
Tile 7:
• From left to right (*)
• From left to down (*)
• From down to right (*)
Tile 9:
From up to right (*)
Tile 96:
• From left to down (*)
• From up to right (*)
Tile A:
From left to up (*)
Tile A5:
• From left to up (*)
• From down to right (*)
Tile B:
• From left to right (*)
• From left to up (*)
• From up to right (*)
2
STANDARD EDITION 1 PROBLEM STATEMENT
Tile C:
From up to down (*)
Tile C3:
• From left to right (*)
• From up to down (*)
Tile D:
• From up to down (*)
• From up to right (*)
• From down to right (*)
Tile E:
• From left to up (*)
• From left to down (*)
• From up to down (*)
Tile F:
• From left to right (*)
• From left to down (*)
• From left to up (*)
• From up to down (*)
• From down to right (*)
• From up to right (*
*/

//define the possible tiles with their paths
Tile tiles[16] = {
    {"3", {LR}},
    {"5", {UD}},
    {"6", {LD}},
    {"7", {LR, LD, UD}},
    {"9", {UR}},
    {"96", {LD, UR}},
    {"A", {LU}},
    {"A5", {LU, DR}},
    {"B", {LR, LU, UR}},
    {"C", {UD}},
    {"C3", {LR, UD}},
    {"D", {UD, UR, DR}},
    {"E", {LU, LD, UD}},
    {"F", {LR, LD, LU, UD, DR, UR}}
};

vector<vector<string>> map;
vector<GoldenPoint> golden_points;
vector<SilverPoint> silver_points;
vector<pair<string, int>> available_tiles;

vector<pair<string, int>> tiles_costs;
vector<SolutionLine> solution ;

void read_input() {
    /*
    10 7 3 4 11 // W H Gn Sm Tl
    2 4
    7 2
    6 6
    4 4 100
    4 2 100
    6 0 150
    7 5 150
    3 6 4
    5 2 6
    6 2 6
    7 8 5
    9 2 7
    A 2 7
    B 8 5
    C 6 5
    D 8 5
    E 8 5
    F 15 3
    */
    
    in >> W >> H >> Gn >> Sm >> Tl;
    golden_points = vector<GoldenPoint>(Gn);
    silver_points = vector<SilverPoint>(Sm);
    available_tiles = vector<pair<string, int>>(Tl);
    tiles_costs = vector<pair<string, int>>(Tl);
    map = vector<vector<string>>(W, vector<string>(H, "0"));

    for(int i = 0; i < Gn; i++) {
        in >> golden_points[i].coord.first >> golden_points[i].coord.second;
        map[golden_points[i].coord.first][golden_points[i].coord.second] = "G";
    }

    for(int i = 0; i < Sm; i++) {
        in >> silver_points[i].coord.first >> silver_points[i].coord.second >> silver_points[i].val;
        map[silver_points[i].coord.first][silver_points[i].coord.second] = to_string(silver_points[i].val);
    }

    for(int i = 0; i < Tl; i++) {
        in >> available_tiles[i].first >> tiles_costs[i].second >> tiles_costs[i].first;
    }
    
    in.close();
}

bool check_solution() {
    // check if solution connects all the golden points looking if theres is a path between each pair of golden points

    //golden points visited
    vector<bool> visited(Gn, false);

    int x, y;

    

    return false;
}

void find_solution() {
    solution = vector<SolutionLine>(16, {"", {}});
    // find solution
    // try all combinations of tiles and check the visited golden points
    // if all golden points are visited, break
    
    vector<int> visited(Gn, 0);
    vector<int> path;
    vector<SolutionLine> solution_prov;

}
void combinations(  ){

}

void find_path(pair<int, int> start, pair<int, int> end, vector<pair<string, int>> tiles) {
    // find a possible path between two points with available tiles
    // use the tiles to find the path
    // if no path is found, return empty vector
    // if path is found, return the path
    // try all possible directions from start with every tile type, follow the path until end is reached
    
    
}
bool find_next_cell(){
    // find the next cell to visit
    // if no cell is found, return false
    // if cell is found, return true
    return false;
    
}
bool optimize_solution() {
    // optimize solution
    return false;
}



int get_score() {
    // get score
   
}



void write_output() {
    // write output
    ofstream out("output.txt");
    for(int i = 0; i < 16; i++) {
        out << solution[i].id << " " ;
        for(auto coord : solution[i].coords) {
            out << coord.first << " " << coord.second << " ";
        }
        out << endl;
    }
    out.close();
}

int main() {
    ios::sync_with_stdio(0);
    cin.tie(0);
    if(DEBUG)
        cout << "Starting" << endl;
    freopen(".txt", "r", stdin);
    freopen("output.txt", "w", stdout);
    
    read_input();
    //
    
    if(DEBUG)
        cout << "Input read" << endl;

    find_solution();
    //cout << "Solution found" << get_score() << endl;
    /* while(optimize_solution()) {
        get_score();
    } */

    write_output();
    if(DEBUG)
        cout << "Output written" << endl;
    
    return 0;
}
