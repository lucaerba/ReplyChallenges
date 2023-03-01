import java.io.*;
import java.util.*;

public class Test {
    static ArrayList<Demon> demons = new ArrayList<>(); //val
    static HashMap<Integer, Demon> sol = new LinkedHashMap<>();
    static Demon[] bsol;
    static int nsol, bsolpt=0, bsolcount=0;
    static int si, sm, t, d;
    static String input = "G:\\Il mio Drive\\PoliTo\\struttureDatiReply\\Pandora\\src\\abyss";

    public static void main(String[] args) {
        System.out.println("leggo");
        readFile();
        demons.sort(new Comparator<Demon>() {
            @Override
            public int compare(Demon o1, Demon o2) {
                return o2.getScore()-o1.getScore();
            }
        });
        System.out.println("findB");
        findBest();
        System.out.println("scrivo");
        writeFile();
    }
    public static void readFile(){
        File file = new File(input);
        try {
            Scanner scanner = new Scanner(file);
            String[] line = scanner.nextLine().split(" ");
            si = Integer.parseInt(line[0]);
            sm = Integer.parseInt(line[1]);
            t = Integer.parseInt(line[2]);
            d = Integer.parseInt(line[3]);

            for(int i = 0; i < d; i++) {
                line = scanner.nextLine().split(" ");
                int sc, tr, sr, na;
                int[] nas;
                sc = Integer.parseInt(line[0]);
                tr = Integer.parseInt(line[1]);
                sr = Integer.parseInt(line[2]);
                na = Integer.parseInt(line[3]);
                nas = new int[na];
                for (int j = 0; j < na; j++) {
                    nas[j] = Integer.parseInt(line[4 + j]);
                }
                demons.add(new Demon(sc, tr, sr, na, nas, i));
            }
        } catch (FileNotFoundException e) {
            e.printStackTrace();
        }
    }
    public static void writeFile(){
        try {
            BufferedWriter br = new BufferedWriter(new FileWriter(input+"out"));
            for (Demon d: bsol) {
                br.write(d.id+"\n");
            }
            br.close();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
    public static void findBest(){
        comb(0,  0, si, 0, 0);
    }
    public static int comb(int pos, int count, int scor, int nt, int curpt) {

        int i;
        //Demon dem;
        //terminazione
        if (pos >= d || nt >= t) {
            if(curpt>bsolpt) {
                bsol = sol.values().toArray(new Demon[0]);
                bsolpt = curpt;
                System.out.println(bsolpt);
                writeFile();
                /*
                if(bsolcount++>=6) {
                    return -1;
                }*/
            }//
                // printf("\n");
            return count+1;
        }
        //#todo aggiungere stamina da mostri prec
        //#todo aggiungere pti da mostri prec

        for (Integer k: sol.keySet()) { //se nturni demone == nt-keyDemone(turno di pos)
            if(sol.get(k).tr == (nt-k.intValue()))
                if(scor+sol.get(k).sr<sm)
                    scor+=sol.get(k).sr;
                else
                    scor=sm;
            if(nt-k.intValue()<sol.get(k).na) curpt+=sol.get(k).nas[nt-k.intValue()];
        }

        //sol successive
        //demone successivo
        //for (i=new Random().nextInt(0, d); i<d; i+=new Random().nextInt(0, d)) {
        for (i = 0; i < d; i++) {
            //se abbastanza stamina
            //dem = demons.get(i);
            if((demons.get(i).preso==0)&&(scor>=demons.get(i).sc)){
                sol.put(nt, demons.get(i));
                demons.get(i).preso = 1;
                count = comb(pos+1,  count, scor-demons.get(i).sc, nt+1, curpt);
                if(count==-1) return -1;
                sol.remove(nt, demons.get(i));
                demons.get(i).preso = 0;
            }
        }
        //dorme
        count = comb(pos, count, scor, nt+1, curpt);
        return count==-1?-1:count;
    }
}
