#include <iostream>
#include <vector>
#include <fstream>

using namespace std;
// input
int R, C, S;
vector<vector<string>> map;

vector<int> snake_length; // snake length
vector<vector<pair<int, int>>> snake_coord; // snake coordinates 
vector<vector<string>> map_snakes;

#define EMPTY "nn"


void read_input() {
    /*
        10 6 5
6 7 5 3 3
1 5 3 6 3 8 5 2 6 8
6 4 * 0 5 3 7 5 2 8
3 4 5 0 3 6 4 * 5 7
3 5 6 3 0 3 5 3 4 6
3 6 7 * 3 0 6 4 5 7
3 7 8 5 3 6 0 4 5 6
    */
    // ifstream in("00-example.txt");
    cin >> C >> R >> S;
    
    map = vector<vector<string>>(R, vector<string>(C));
    snake_length = vector<int>(S);
    snake_coord = vector<vector<pair<int, int>>>(S*2);
    map_snakes = vector<vector<string>>(R, vector<string>(C));

    for (int i = 0; i < S; i++) {
        cin >> snake_length[i];
        snake_coord[i] = vector<pair<int, int>>(snake_length[i]);
    }

    for (int i = 0; i < R; i++) {
        for (int j = 0; j < C; j++) {
            cin >> map[i][j];
            
            if(map[i][j] == "*" ) {
                map_snakes[i][j] = "*";
            }else {
                map_snakes[i][j] = EMPTY;
            }
        }
    }
    // in.close();

    
}

void find_solution() {
    // find solution
    
    /*     //position the snakes in the map randomly checking not wormholes or other snakes
        for (int i = 0; i < S; i++) {
            int x = rand() % R;
            int y = rand() % C;
            while (map_snakes[x][y] == "*" || map_snakes[x][y] != EMPTY) {
                x = rand() % R;
                y = rand() % C;
            }
            snake_coord[i][0] = {x, y};
            map_snakes[x][y] = "H" + to_string(i);
        }
     */
    // position the rest of the snake in the map randomly checking not wormholes or other snakes and looking for the cell with max value, 
    // if the cell has a snake, we look for the next cell with max value in the 4 adjacents. There's pac man effect, if the snake is in the border of the map, 
    // the next cell with max value is the opposite border of the map
    for (int i = 0; i < S; i++) {
        // cout << "Snake " << i << " " << snake_length[i] << endl;
        // position the head of the snake in the best cell, not wormholes or other snakes, not random, and checking enought space for the snake
        int max_value = INT16_MIN;
        int max_x = -1;
        int max_y = -1;
        for (int j = 0; j < R; j++) {
            for (int k = 0; k < C; k++) {
                if (map[j][k] != "*" && map_snakes[j][k] == EMPTY) {
                    if (stoi(map[j][k]) > max_value) {
                        max_value = stoi(map[j][k]);
                        max_x = j;
                        max_y = k;
                    }
                }
            }
        }
        if(max_x == -1 || max_y == -1){
            snake_length[i] = 0;
            continue;
        }
        snake_coord[i][0] = {max_x, max_y};
        map_snakes[max_x][max_y] = "H" + to_string(i);
    

        for (int j = 1; j < snake_length[i]; j++) {
            int x = snake_coord[i][j - 1].first;
            int y = snake_coord[i][j - 1].second;
            max_value = INT16_MIN;
            max_x = -1;
            max_y = -1;
            int best_w_x = -1;
            int best_w_y = -1;
            int old_w_x = -1;
            int old_w_y = -1;

            for (int k = -1; k <= 1; k++) {
                for (int l = -1; l <= 1; l++) {
                    //exclude the diagonals too and same cell
                    if (k == 0 && l == 0) {
                        continue;
                    }
                    if (k == -1 && l == -1 || k == -1 && l == 1 || k == 1 && l == -1 || k == 1 && l == 1) {
                        continue;
                    }
                    
                    int new_x = (x + k + R) % R;
                    int new_y = (y + l + C) % C;
    
                    if (map[new_x][new_y] != "*" && map_snakes[new_x][new_y] == EMPTY) {
                        if (stoi(map[new_x][new_y]) > max_value) {
                            max_value = stoi(map[new_x][new_y]);
                            max_x = new_x;
                            max_y = new_y;
                            best_w_x = -1;
                            best_w_y = -1;
                        }
                    }

                    
                    
                    // if there is a warmhole choose the best adjacent cell of another warmhole
                    if (map[new_x][new_y] == "*" && j < snake_length[i] - 2) {
                        // check if snake_cord doesnt contain already that warmhole that is already been used by the warm
                        bool already_used = false;
                        for(int m = 0; m < j; m++){
                            if(snake_coord[i][m].first == new_x && snake_coord[i][m].second == new_y){
                                already_used = true;
                                continue;
                            }
                        }
                        if(already_used){
                            continue;
                        }

                        for (int m = 0; m < R; m++) {
                            for (int n = 0; n < C; n++) {
                                if(m == new_x && n == new_y){
                                    continue;
                                }
                                if (map[m][n] == "*") {
                                    // find the best adjacent cell of the warmhole
                                    for (int o = -1; o <= 1; o++) {
                                        for (int p = -1; p <= 1; p++) {
                                            //exclude the diagonals too and same cell
                                            if (o == 0 && p == 0) {
                                                continue;
                                            }
                                            if (o == -1 && p == -1 || o == -1 && p == 1 || o == 1 && p == -1 || o == 1 && p == 1) {
                                                continue;
                                            }
                                            
                                            int new_m = (m + o + R) % R;
                                            int new_n = (n + p + C) % C;
                                            if (map[new_m][new_n] != "*" && map_snakes[new_m][new_n] == EMPTY) {
                                                if (stoi(map[new_m][new_n]) > max_value) {
                                                    max_value = stoi(map[new_m][new_n]);
                                                    max_x = new_m;
                                                    max_y = new_n;
                                                    best_w_x = m;
                                                    best_w_y = n;
                                                    old_w_x = new_x;
                                                    old_w_y = new_y;
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        
                    }
                }
            }

            if(max_x == -1 || max_y == -1){
                snake_length[i] = 0;
                //clean the cells were the snake was positioned
                for (int k = 0; k < j; k++) {
                    //if not warmhole
                    if(map[snake_coord[i][k].first][snake_coord[i][k].second] != "*"){
                        map_snakes[snake_coord[i][k].first][snake_coord[i][k].second] = EMPTY;
                    }
                }
                break;
            }

            if(best_w_x != -1 && best_w_y != -1){ // if there is a best warmhole
                snake_coord[i][j] = {old_w_x, old_w_y};
                j++;
                snake_coord[i][j] = {best_w_x, best_w_y};
                j++;
                snake_length[i]+=1;
                // map_snakes[best_w_x][best_w_y] = "i" + to_string(i);
            }
            snake_coord[i][j] = {max_x, max_y};
            map_snakes[max_x][max_y] = "i" + to_string(i);
        }
    }

}

bool optimize_solution() {
    // optimize solution
    return false;
}

int get_score_single_snake(int snake_index) {
    // get score for single snake
    vector<pair<int, int>> snake = snake_coord[snake_index];
    int score = 0;
    for (int i = 0; i < snake.size(); i++) {
        int x = snake[i].first;
        int y = snake[i].second;
        if (map[x][y] != "*") {
            score += stoi(map[x][y]);
        }
    }
    return score;
}

int get_score() {
    // get score
    int total_score = 0;
    for (int i = 0; i < S; i++) {
        total_score += get_score_single_snake(i);
    }
    
    return total_score;
}



void write_output() {
    // write output 1 row for each snake, if warmhole print coordinates of jumping, no warmhole print the path, checking from head if go right R, left L, up U, down D
    /*
    0 0 R R D 7 2 R R
    6 1 L U L D L U
    1 1 R 3 4 R R R
    7 1 D 3 4 L
    9 0 U L
    */
   
    for (int i = 0; i < S; i++) {
        if (snake_length[i] == 0) {
            cout << endl;
            continue;
        }
        cout <<  snake_coord[i][0].second << " " << snake_coord[i][0].first << " ";
        for (int j = 1; j < snake_length[i]; j++) {
            // check if is a warmhole
            
            if (snake_coord[i][j].first == snake_coord[i][j - 1].first) {
                if (snake_coord[i][j].second == (snake_coord[i][j - 1].second + 1) % C) {
                    cout << "R ";
                } else {
                    cout << "L ";
                }
            } else {
                if (snake_coord[i][j].first == (snake_coord[i][j - 1].first + 1) % R) {
                    cout << "D ";
                } else {
                    cout << "U ";
                }
            }
            if (map[snake_coord[i][j].first][snake_coord[i][j].second] == "*") {
                //check if the previous cell was L,R,U,D respect to the warmhole
                j++;
                cout << snake_coord[i][j].second << " " << snake_coord[i][j].first << " ";
                continue;
            }
        }
        cout << endl;
    }

    
}

int main() {
    ios::sync_with_stdio(0);
    cin.tie(0);
    cout << "Starting" << endl;
    freopen("01-chilling-cat.txt", "r", stdin);
    freopen("output.txt", "w", stdout);
    
    read_input();
    //cout << "Input read" << endl;

    find_solution();
    //cout << "Solution found" << get_score() << endl;
    /* while(optimize_solution()) {
        get_score();
    } */

    write_output();
    //cout << "Output written" << endl;
    //print map_snakes
    for (int i = 0; i < R; i++) {
        for (int j = 0; j < C; j++) {
            cout << map_snakes[i][j] << " ";
        }
        cout << endl;
    }  
    return 0;
}
