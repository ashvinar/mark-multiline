/* Small translation estimate on 24x27 camera thumbnails. It matches gradients
 * inside the image, so a stationary border and exposure shifts cannot dominate.
 * No text recognition, font parameters, heap allocation or platform APIs. */
#ifndef FN
#define FN(name)
#endif
struct movement {int dx,dy;unsigned zero,best,runner,energy;};
static inline unsigned magnitude(int x){return x<0?(unsigned)-x:(unsigned)x;}

FN("mark_motion") int mark_motion(const unsigned char *previous,
                                  const unsigned char *current,
                                  struct movement *out) {
    unsigned scores[91],best=~0u,energy=0,zero=0;int bx=0,by=0;
    for(int y=4;y<23;y++)for(int x=6;x<17;x++) {
        int p=y*24+x;
        energy+=magnitude((int)previous[p+1]-previous[p]);
        energy+=magnitude((int)previous[p+24]-previous[p]);
    }
    for(int dy=-3;dy<=3;dy++)for(int dx=-6;dx<=6;dx++) {
        unsigned score=0;
        for(int y=4;y<23;y++)for(int x=6;x<17;x++) {
            int p=y*24+x,c=(y+dy)*24+x+dx;
            score+=magnitude(((int)current[c+1]-current[c])-
                             ((int)previous[p+1]-previous[p]));
            score+=magnitude(((int)current[c+24]-current[c])-
                             ((int)previous[p+24]-previous[p]));
        }
        scores[(dy+3)*13+dx+6]=score;
        if(!dx&&!dy)zero=score;
        if(score<best || (score==best &&
           magnitude(dx)+magnitude(dy)<magnitude(bx)+magnitude(by))) {
            best=score;bx=dx;by=dy;
        }
    }
    unsigned runner=~0u;
    for(int dy=-3;dy<=3;dy++)for(int dx=-6;dx<=6;dx++) {
        unsigned score=scores[(dy+3)*13+dx+6];
        if(magnitude(dx-bx)+magnitude(dy-by)>1 && score<runner)runner=score;
    }
    out->dx=bx;out->dy=by;out->zero=zero;out->best=best;
    out->runner=runner;out->energy=energy;
    /* Faint but well-matched text is useful too. Demand a stronger fit close
     * to the noise floor instead of imposing one ink-contrast threshold. */
    return energy>209u*3 && (energy>209u*12 || best*2<energy) &&
           best*5<energy*4 && best*5<zero*4 &&
           best*20<runner*19;
}
