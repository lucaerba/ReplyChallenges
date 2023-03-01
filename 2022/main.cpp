//
// Created by lucaerba on 3/1/23.
//

#include "libraries.h"

using namespace std;
void readFile();

int main() {
    readFile();
    return 0;
}

void readFile(){
    int i;
    srand(time(NULL));
    #pragma omp parallel for
    for (int j = 0; j < 42; ++j) {
        cout << j << "\n";
        sleep(rand()%10);
    }
}

void printFile(){

}