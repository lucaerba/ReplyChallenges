#include <iostream>
#include <vector>
#include <fstream>
#include <set>
#include <stack>
#include <algorithm>
#define DEBUG 1

#define INPUT 0
using namespace std;
// input vars

//input files



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
vector<pair<string, int>> available_tiles; // tile id, number of tiles
vector<pair<string, int>> tiles_costs; // tile id, cost
vector<SolutionLine> solution ;
//get tile
Tile get_tile(string id) {
    for(int i = 0; i < 16; i++) {
        if(tiles[i].id == id)
            return tiles[i];
    }
    return {"", {}};
}
bool check_visited(vector<bool> visited) {
    // check if all golden points are visited
    for(int i = 0; i < Gn; i++) {
        if(!visited[i])
            return false;
    }
    return true;
}

bool move_next(pair<int, int> current, int direction, vector<bool>& visited, vector<vector<string>>& map) {
    // move to the next cell
    // if the cell is a golden point, mark it as visited
    // if the cell is a silver point, add the value to the score
    // if the cell is a wall, return false
    // if the cell is a tile, move to the next cell
    // if the cell is the end, return true
    if(check_visited(visited))
        return true;
    
    if(map[current.first][current.second] == "G") {
        for(int i = 0; i < Gn; i++) {
            if(golden_points[i].coord == current) {
                visited[i] = true;
                break;
            }
        }
    }
    int x_start = current.first;
    int y_start = current.second;
    //move to next possible directions checking neighboughrs tiles, avoiding the direction you came from
    for(int i=-1; i<2; i++) {
        for(int j=-1; j<2; j++) {
            if(i == 0 && j == 0)
                continue;
            if(x_start + i < 0 || x_start + i >= W || y_start + j < 0 || y_start + j >= H)
                continue;
            //get the tile
            if(map[x_start + i][y_start + j] == "0")
                continue;
            Tile tile = get_tile(map[x_start + i][y_start + j]);
            //depending on tile type move to the next cell-> 3 LR, 5 UD, 6 LU, 7 LD, 9 UR, 96 DR, A LU, A5 DR, B LR, C UD, C3 LR, D UD, E LU, F LR
            if(tile.id == "3") {
                //move left to right
                move_next({x_start + i, y_start}, LR, visited, map);
            }else if (tile.id == "5"){
                //move up to down
                move_next({x_start, y_start + j}, UD, visited, map);
            }else if (tile.id == "6"){
                //move left to down
                move_next({x_start + i, y_start + j}, LD, visited, map);
            }else if (tile.id == "7"){
                //move left to right, left to down, down to right
                move_next({x_start + i, y_start}, LR, visited, map);
                move_next({x_start + i, y_start + j}, LD, visited, map);
                move_next({x_start, y_start + j}, UD, visited, map);
            }else if (tile.id == "9"){
                //move up to right
                move_next({x_start, y_start + j}, UR, visited, map);
            }else if (tile.id == "96"){
                //move left to down, up to right
                move_next({x_start + i, y_start + j}, LD, visited, map);
                move_next({x_start, y_start + j}, UR, visited, map);
            }else if (tile.id == "A"){
                //move left to up
                move_next({x_start + i, y_start}, LU, visited, map);
            }else if (tile.id == "A5"){
                //move left to up, down to right
                move_next({x_start + i, y_start}, LU, visited, map);
                move_next({x_start, y_start + j}, DR, visited, map);
            }else if (tile.id == "B"){
                //move left to right, left to up, up to right
                move_next({x_start + i, y_start}, LR, visited, map);
                move_next({x_start + i, y_start}, LU, visited, map);
                move_next({x_start, y_start + j}, UR, visited, map);
            }else if (tile.id == "C"){
                //move up to down
                move_next({x_start, y_start + j}, UD, visited, map);
            }else if (tile.id == "C3"){
                //move left to right, up to down
                move_next({x_start + i, y_start}, LR, visited, map);
                move_next({x_start, y_start + j}, UD, visited, map);
            }else if (tile.id == "D"){
                //move up to down, up to right, down to right
                move_next({x_start, y_start + j}, UD, visited, map);
                move_next({x_start, y_start + j}, UR, visited, map);
                move_next({x_start + i, y_start + j}, DR, visited, map);
            }else if (tile.id == "E"){
                //move left to up, left to down, up to down
                move_next({x_start + i, y_start}, LU, visited, map);
                move_next({x_start + i, y_start + j}, LD, visited, map);
                move_next({x_start, y_start + j}, UD, visited, map);
            }else if (tile.id == "F"){
                //move left to right, left to down, left to up, up to down, down to right, up to right
                move_next({x_start + i, y_start}, LR, visited, map);
                move_next({x_start + i, y_start + j}, LD, visited, map);
                move_next({x_start + i, y_start}, LU, visited, map);
                move_next({x_start, y_start + j}, UD, visited, map);
                move_next({x_start + i, y_start + j}, DR, visited, map);
                move_next({x_start, y_start + j}, UR, visited, map);
            }
            
        }
    }
    return false;

}


bool check_solution(vector<vector<string>> map, vector<SolutionLine> solution_prov) {
    // check if solution connects all the golden points looking if theres is a path between each pair of golden points
    // moving into the map check if you can reach all the golden points, starting from the first one
    //golden points visited
    vector<bool> visited(Gn, false);
    if(DEBUG)
        cout << "Checking solution" << endl;
    int x_start = golden_points[0].coord.first;
    int y_start = golden_points[0].coord.second;
    bool ret = false;
    //move from the start in all available directions up, down, left, right, checking neighbors tiles
    for(int i=-1; i<2; i++) {
        for(int j=-1; j<2; j++) {
            if(i == 0 && j == 0)
                continue;
            if(x_start + i < 0 || x_start + i >= W || y_start + j < 0 || y_start + j >= H)
                continue;
            //get the tile
            if(map[x_start + i][y_start + j] == "0")
                continue;
            Tile tile = get_tile(map[x_start + i][y_start + j]);
            //depending on tile type move to the next cell-> 3 LR, 5 UD, 6 LU, 7 LD, 9 UR, 96 DR, A LU, A5 DR, B LR, C UD, C3 LR, D UD, E LU, F LR
            if(tile.id == "3") {
                //move left to right
                if (move_next({x_start + i, y_start}, LR, visited, map))
                    ret = true;
            }else if (tile.id == "5"){
                //move up to down
                if (move_next({x_start, y_start + j}, UD, visited, map))
                    ret = true;
            }else if (tile.id == "6"){
                //move left to down
                if (move_next({x_start + i, y_start + j}, LD, visited, map))
                    ret = true;
            }else if (tile.id == "7"){
                //move left to right, left to down, down to right
                if (move_next({x_start + i, y_start}, LR, visited, map))
                    ret = true;
                if (move_next({x_start + i, y_start + j}, LD, visited, map))
                    ret = true;
                if (move_next({x_start, y_start + j}, UD, visited, map))
                    ret = true;
            }else if (tile.id == "9"){
                //move up to right
                if (move_next({x_start, y_start + j}, UR, visited, map))
                    ret = true;
            }else if (tile.id == "96"){
                //move left to down, up to right
                if (move_next({x_start + i, y_start + j}, LD, visited, map))
                    ret = true;
                if (move_next({x_start, y_start + j}, UR, visited, map))
                    ret = true;
            }else if (tile.id == "A"){
                //move left to up
                if (move_next({x_start + i, y_start}, LU, visited, map))
                    ret = true;
            }else if (tile.id == "A5"){
                //move left to up, down to right
                if (move_next({x_start + i, y_start}, LU, visited, map))
                    ret = true;
                if (move_next({x_start, y_start + j}, DR, visited, map))
                    ret = true;
            }else if (tile.id == "B"){
                //move left to right, left to up, up to right
                if (move_next({x_start + i, y_start}, LR, visited, map))
                    ret = true;
                if (move_next({x_start + i, y_start}, LU, visited, map))
                    ret = true;
                if (move_next({x_start, y_start + j}, UR, visited, map))
                    ret = true;
            }else if (tile.id == "C"){
                //move up to down
                if (move_next({x_start, y_start + j}, UD, visited, map))
                    ret = true;
            }else if (tile.id == "C3"){
                //move left to right, up to down
                if (move_next({x_start + i, y_start}, LR, visited, map))
                    ret = true;
                if (move_next({x_start, y_start + j}, UD, visited, map))
                    ret = true;
            }else if (tile.id == "D"){
                //move up to down, up to right, down to right
                if (move_next({x_start, y_start + j}, UD, visited, map))
                    ret = true;
                if (move_next({x_start, y_start + j}, UR, visited, map))
                    ret = true;
                if (move_next({x_start + i, y_start + j}, DR, visited, map))
                    ret = true;
            }else if (tile.id == "E"){
                //move left to up, left to down, up to down
                if (move_next({x_start + i, y_start}, LU, visited, map))
                    ret = true;
                if (move_next({x_start + i, y_start + j}, LD, visited, map))
                    ret = true;
                if (move_next({x_start, y_start + j}, UD, visited, map))
                    ret = true;
            }else if (tile.id == "F"){
                //move left to right, left to down, left to up, up to down, down to right, up to right
                if (move_next({x_start + i, y_start}, LR, visited, map))
                    ret = true;
                if (move_next({x_start + i, y_start + j}, LD, visited, map))
                    ret = true;
                if (move_next({x_start + i, y_start}, LU, visited, map))
                    ret = true;
                if (move_next({x_start, y_start + j}, UD, visited, map))
                    ret = true;
                if (move_next({x_start + i, y_start + j}, DR, visited, map))
                    ret = true;
                if (move_next({x_start, y_start + j}, UR, visited, map))
                    ret = true;
            }
        }
    }

    return ret;
}


bool find_solution_recursive(pair<int, int> current, vector<SolutionLine> solution_prov, vector<vector<string>> map_sol, vector<pair<string, int>> tiles_for_sol) {
    //place an available tile on the map, then go to the next cell, try all the type of tiles available, also not placing the tile
    if(current.first == W && current.second == H) {
        //check if the solution is valid
        if(check_solution(map_sol, solution_prov)) {
            solution = solution_prov;
            map = map_sol;
            if(DEBUG){
                cout << "Solution found" << endl;
                //print map
                for(int i = 0; i < W; i++) {
                    for(int j = 0; j < H; j++) {
                        cout << map[i][j] << " ";
                    }
                    cout << endl;
                }
            }
            return true;
        }
        return false;
    }
    //place a tile
    if (DEBUG)
        cout << "Current cell: " << current.first << " " << current.second << endl;
    for(int i = 0; i < tiles_for_sol.size(); i++) {
        if(tiles_for_sol[i].second == 0 )
            continue;
        if(map_sol[current.first][current.second] == "G"){
            //move to the next cell
            if(current.first == W) {
                if( find_solution_recursive({0, current.second + 1}, solution_prov, map_sol, tiles_for_sol))
                    return true;
            }else {
                if(find_solution_recursive({current.first + 1, current.second}, solution_prov, map_sol, tiles_for_sol))
                    return true;
            }
        }else{
            //place the tile 
            map_sol[current.first][current.second] = tiles_for_sol[i].first;
            //decrease the number of tiles
            tiles_for_sol[i].second--;
            //move to the next cell
            if(current.first == W) {
                if( find_solution_recursive({0, current.second + 1}, solution_prov, map_sol, tiles_for_sol))
                    return true;
            }else {
                if(find_solution_recursive({current.first + 1, current.second}, solution_prov, map_sol, tiles_for_sol))
                    return true;
            }
            //place the tile 
            map_sol[current.first][current.second] = "0";
            //decrease the number of tiles
            tiles_for_sol[i].second++;
        }
        
    }

}

void find_solution() {
    solution = vector<SolutionLine>(16, {"", {}});
    // find solution
    // try all combinations of tiles and check the visited golden points
    // if all golden points are visited, break
    
    vector<SolutionLine> solution_prov = vector<SolutionLine>(16, {"", {}});\
    //copy the map
    vector<vector<string>> map_sol = map;
    vector<pair<string, int>> tiles_for_sol ;
    
    // try all the combination of tiles on the map, position them on solution_prov and map_sol, then use check_solution to check if the solution is valid
    // if it is valid, break
    find_solution_recursive({0, 0}, solution_prov, map_sol, available_tiles);
    
}


bool optimize_solution() {
    // optimize solution
    return false;
}



int get_score() {
    // get score
   
}


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
//ifstream in("01-comedy.txt");
//ifstream in("02-sentimental.txt");
//ifstream in("03-adventure.txt");
//ifstream in("04-drama.txt");
//ifstream in("05-horror.txt");
    cin >> W >> H >> Gn >> Sm >> Tl;

    if(DEBUG)  
        cout << W << " " << H << " " << Gn << " " << Sm << " " << Tl << endl;
    golden_points = vector<GoldenPoint>(Gn);
    silver_points = vector<SilverPoint>(Sm);
    available_tiles = vector<pair<string, int>>(Tl);
    tiles_costs = vector<pair<string, int>>(Tl);
    map = vector<vector<string>>(W, vector<string>(H, "0"));

    for(int i = 0; i < Gn; i++) {
        cin >> golden_points[i].coord.first >> golden_points[i].coord.second;
        map[golden_points[i].coord.first][golden_points[i].coord.second] = "G";
    }
    if(DEBUG)
        cout << "Golden points read" << endl;
    for(int i = 0; i < Sm; i++) {
        cin >> silver_points[i].coord.first >> silver_points[i].coord.second >> silver_points[i].val;
        map[silver_points[i].coord.first][silver_points[i].coord.second] = to_string(silver_points[i].val);
    }
    if(DEBUG)
        cout << "Silver points read" << endl;
    for(int i = 0; i < Tl; i++) {
        
        cin >> available_tiles[i].first >> available_tiles[i].second >> tiles_costs[i].second;
        tiles_costs[i].first = available_tiles[i].first;
        if(DEBUG)
            cout << available_tiles[i].first << " " << tiles_costs[i].second << " " << tiles_costs[i].first << endl;
    }
    if(DEBUG)
        cout << "Tiles read" << endl;
}

void write_output() {
    // write output
    for(int i = 0; i < 16; i++) {
        cout << solution[i].id << " " ;
        for(auto coord : solution[i].coords) {
            cout << coord.first << " " << coord.second << " ";
        }
        cout << endl;
    }
}

int main() {
    ios::sync_with_stdio(0);
    cin.tie(0);
    cout << "Starting" << endl;
    freopen("01-comedy.txt", "r", stdin);
    freopen("output.txt", "w", stdout);
    if(DEBUG)
        cout << "Starting" << endl;
    
    read_input();
    //
    
    if(DEBUG)
        cout << "Input read" << endl;

    if(DEBUG) { //print map
        cout << "Map" << endl;
        for(int i = 0; i < W; i++) {
            for(int j = 0; j < H; j++) {
                cout << map[i][j] << " ";
            }
            cout << endl;
        }
    }
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
