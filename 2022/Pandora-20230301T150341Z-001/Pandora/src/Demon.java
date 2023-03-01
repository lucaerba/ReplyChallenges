public class Demon {
    int sc, tr, sr, na;
    int id;
    int[] nas;
    int preso=0;

    public Demon(int sc, int tr, int sr, int na, int[] nas, int id) {
        this.sc = sc;
        this.tr = tr;
        this.sr = sr;
        this.na = na;
        this.nas = nas;
        this.id = id;
    }
    public int getpttot(){
        int ret=0;
        for (int i = 0; i < na; i++) {
            ret+=nas[i];
        }
        return ret;
    }
    public int getScore(){
        //o2.getpttot(t)*o2.sr/(o2.tr*o2.sc)
        if(sr/sc>1) return getpttot()*sr*10/(tr);
        return getpttot()*sr/10;
        //int ret = (int)(getpttot()*(sr/sc));
        //return ret;
    }

}
