/* Held-button capture controller. Hardware SDK and ordinary image worker remain
 * unchanged. All split decisions occur before submitting camera frames. */
typedef unsigned int u32;
typedef unsigned char u8;
typedef __SIZE_TYPE__ usize;
#define FN(name) __attribute__((section(".text." name),used))
#define INLINE static __attribute__((always_inline)) inline
#include "motion.c"
#define OFF 0u
#define LINE 1u
#define FINISHING 2u
#define WAIT_PAPER 3u
#define FAILED 4u
#define SAMPLE_CAPACITY 1024u
/* Require sustained camera contact before arming another lift. This rejects
 * short focus flashes during the return stroke without discarding touch-down
 * frames: they are still submitted immediately. */
#define ARM_FRAMES 20u
/* At the observed 120 fps, require about 50 ms of definite defocus. A white
 * region or mildly softened text is ambiguous and must keep reaching the SDK. */
#define LIFT_FRAMES 6u
#define UNCERTAIN 2
#define CAMERA_CAPACITY 512u
#define CAMERA_PIXELS (24u*27u)
struct camera_sample {
    u32 serial,time,phase,sdk_before,sdk_after,pushes,rejections,last_push;
    u32 callback_result,width,height,edge,range,generation;
    u8 pixels[CAMERA_PIXELS];
};
struct sample {u32 frame, edge, range, phase;};
struct state {
    u32 generation, phase, observed, seen, blanks, frames, count, rotations;
    u32 width,height,physical_address,bytes,errors,would_rotate;
#ifndef MARK_MONITOR_ONLY
    u32 saved;
#endif
    struct sample samples[SAMPLE_CAPACITY];
#ifdef MARK_MONITOR_ONLY
    u32 snapshot_width,snapshot_height,snapshot_bytes,snapshot_edge;
    u8 snapshot[16384];
#endif
    u32 camera_frames,camera_records,pushes,rejections,last_push;
    struct camera_sample camera[CAMERA_CAPACITY];
    u32 previous_valid,current_energy,reference_energy,energy_low,moving_samples;
    int direction_vote,direction;
    u32 forward_recent;
    u8 previous[CAMERA_PIXELS];
    u32 queue_lock,pending_frame,pending_handle,pending_index,pending_generation;
    u32 queue_head,queue_count,queue_capacity,queue_peak,queue_sent,queue_released,queue_errors,queue_fallbacks;
    u32 queue_frames[8],queue_handles[8],queue_indices[8];
    u32 pool_observed;
};
__attribute__((section(".mark_layout"),used))
const u32 mark_state_bytes=sizeof(struct state);
#ifndef MARK_STATE
#define MARK_STATE 0x7cd80u
#endif
#define S ((struct state *)MARK_STATE)
#ifndef MARK_WORKER_TRAMPOLINE
#error Define the encoder trampoline address from the ELF layout
#endif
INLINE u32 load(u32 *p) {return __atomic_load_n(p,__ATOMIC_ACQUIRE);}
INLINE void set(u32 *p,u32 v) {__atomic_store_n(p,v,__ATOMIC_RELEASE);}
INLINE u32 held(void) {return ((u32 (*)(void))0x4909du)();}
INLINE int original_push(u32 handle,u32 index,u32 *frame) {
    int result=((int (*)(u32,u32,u32 *))0x209a8u)(handle,index,frame);
    if(load(&S->phase)!=OFF) {
        S->pushes++;if(result)S->rejections++;
        S->last_push=(u32)result;
    }
    return result;
}
/* The original scan key handlers already own this mutex. The controller takes
 * it too, so physical release and a line rotation cannot stop/start in parallel. */
#ifndef MARK_KEY_MUTEX
#error Define the independently resolved application key mutex address
#endif
INLINE void lock_key(void) {((int (*)(void *))0x20be4u)((void *)MARK_KEY_MUTEX);}
INLINE void unlock_key(void) {((int (*)(void *))0x20984u)((void *)MARK_KEY_MUTEX);}
void mark_rotate(u32 generation);
void mark_continue(u32 generation);
void mark_flush(u32 send);
void mark_handoff(void);
INLINE u32 buffer_capacity(void) {
    u32 head=0x7c660u,node=*(volatile u32 *)head,count=0,seen[10];
    /* Ten distinct slots already prove room for our maximum eight plus two
     * native slots. A larger valid pool must not disable buffering. */
    while(node && node!=head && count<10) {
        if(node&3u){S->pool_observed=0;return 0;}
        for(u32 i=0;i<count;i++)if(seen[i]==node){S->pool_observed=0;return 0;}
        seen[count++]=node;node=*(volatile u32 *)node;
    }
    S->pool_observed=count;
    if(!node)return 0;
    return count>3?count-2:(count>1?count-1:0);
}
INLINE void queue_lock(void) {
    while(__atomic_exchange_n(&S->queue_lock,1,__ATOMIC_ACQUIRE)){}
}
INLINE void queue_unlock(void){set(&S->queue_lock,0);}
INLINE void release_frame(u32 frame) {
    if(((int (*)(u32))0x4c0bdu)(frame)) {S->queue_errors++;S->errors++;}
    S->queue_released++;
}
INLINE void send_frame(u32 handle,u32 index,u32 frame) {
    if(original_push(handle,index,(u32 *)frame)) {
        S->queue_errors++;S->errors++;release_frame(frame);
    } else S->queue_sent++;
}
/* Caller holds the short queue lock. Frames here have already been retained
 * and counted by the original camera callback, so the original pop callback
 * balances ownership if a frame cannot be submitted. */
INLINE void drain_queue(u32 send) {
    while(S->queue_count) {
        u32 n=S->queue_head;S->queue_head=(n+1)&7u;S->queue_count--;
        if(send)send_frame(S->queue_handles[n],S->queue_indices[n],S->queue_frames[n]);
        else release_frame(S->queue_frames[n]);
    }
}
INLINE void begin_line(void) {
    /* Relearn detail strength for each line; the previous line's ink/contrast
     * must not become a fixed threshold for a different next line. */
    S->reference_energy=0;S->moving_samples=0;S->energy_low=0;
    set(&S->phase,LINE);
}
FN("mark_flush") void mark_flush(u32 send) {
    queue_lock();drain_queue(send);queue_unlock();
}

FN("mark_handoff") void mark_handoff(void) {
    u32 frame=S->pending_frame;if(!frame)return;
    S->pending_frame=0;
    queue_lock();
    u32 phase=load(&S->phase);
    if(S->pending_generation!=load(&S->generation) ||
       (phase!=WAIT_PAPER && phase!=LINE))release_frame(frame);
    else if(phase==LINE)send_frame(S->pending_handle,S->pending_index,frame);
    else {
        /* At capacity, submit every retained frame rather than silently
         * overwriting input or exhausting the camera's own buffer pool. */
        if(S->queue_count==S->queue_capacity) {
            S->queue_fallbacks++;drain_queue(1);begin_line();
            send_frame(S->pending_handle,S->pending_index,frame);
        } else {
            u32 n=(S->queue_head+S->queue_count)&7u;
            S->queue_frames[n]=frame;S->queue_handles[n]=S->pending_handle;
            S->queue_indices[n]=S->pending_index;S->queue_count++;
            if(S->queue_count>S->queue_peak)S->queue_peak=S->queue_count;
            if((S->seen>=3 && (S->forward_recent || !S->direction)) ||
               S->queue_count==S->queue_capacity) {
                if(!S->forward_recent)S->queue_fallbacks++;
                drain_queue(1);begin_line();
            }
        }
    }
    queue_unlock();
}

INLINE void rotate_if_active(void) {
    u32 expected=LINE;
    if(!__atomic_compare_exchange_n(&S->phase,&expected,FINISHING,0,
                                    __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    int queued=((int (*)(void (*)(u32),u32))0x4c805u)(mark_rotate,load(&S->generation));
    if(queued){S->errors++;S->blanks=0;set(&S->phase,LINE);}
}

INLINE void observe_movement(const u8 *pixels) {
    u32 energy=0;
    for(u32 y=4;y<23;y++)for(u32 x=6;x<17;x++) {
        u32 p=y*24+x;
        energy+=magnitude((int)pixels[p+1]-pixels[p]);
        energy+=magnitude((int)pixels[p+24]-pixels[p]);
    }
    S->current_energy=energy;
    if(S->forward_recent)S->forward_recent--;
    if(S->previous_valid) {
        struct movement motion;
        int valid=mark_motion(S->previous,pixels,&motion);
        if(valid && magnitude(motion.dy)<=1 && motion.dx) {
            int direction=motion.dx<0?-1:1;
            if(!S->direction) {
                S->direction_vote+=direction;
                if(S->direction_vote>=3)S->direction=1;
                if(S->direction_vote<=-3)S->direction=-1;
            }
            if(direction==S->direction) {
                S->forward_recent=3;
                if(load(&S->phase)==LINE) {
                    S->reference_energy=S->reference_energy?
                        (S->reference_energy*7+energy)/8:energy;
                    S->moving_samples++;
                }
            }
        }
        if(load(&S->phase)==LINE && S->seen>=ARM_FRAMES &&
           S->moving_samples>=3 && S->reference_energy &&
           energy*3<S->reference_energy) {
            if(++S->energy_low>=3) {S->energy_low=0;rotate_if_active();}
        } else S->energy_low=0;
    }
    for(u32 i=0;i<CAMERA_PIXELS;i++)S->previous[i]=pixels[i];
    S->previous_valid=1;
}

FN("mark_down") int mark_down(u32 key) {
    if(key==0xa9u) {
        mark_flush(0);
        __atomic_fetch_add(&S->generation,1,__ATOMIC_ACQ_REL);
        S->camera_frames=0;set(&S->camera_records,0);
        S->pushes=0;S->rejections=0;S->last_push=0;
        S->previous_valid=0;S->current_energy=0;S->reference_energy=0;
        S->energy_low=0;S->moving_samples=0;S->direction_vote=0;
        S->direction=0;S->forward_recent=0;S->pending_frame=0;
        S->queue_capacity=buffer_capacity();S->queue_head=0;
        S->queue_peak=0;S->queue_sent=0;S->queue_released=0;
        S->queue_errors=0;S->queue_fallbacks=0;
        set(&S->phase,LINE);
    }
    return ((int (*)(u32))0x4df65u)(key);
}

FN("mark_rotate") void mark_rotate(u32 generation) {
    lock_key();
    if(generation!=load(&S->generation)||!held()||load(&S->phase)!=FINISHING) {
        unlock_key(); return;
    }
    /* Run the complete normal key-up path, including exposure and camera
       state changes. It queues the normal capture-completion worker. */
    int released=((int (*)(u32,u32,u32,u32))0x4db7du)(0xa9,0,500,1);
    if(!released || !*(volatile u32 *)0x7c880u ||
       ((int (*)(void (*)(u32),u32))0x4c805u)(mark_continue,generation)) {
        S->errors++;set(&S->phase,FAILED);
    }
    unlock_key();
}

FN("mark_continue") void mark_continue(u32 generation) {
    lock_key();
    if(generation==load(&S->generation) && load(&S->phase)==FINISHING) {
        /* FIFO queue places this after the normal completion/copy worker. */
        int started=((int (*)(u32))0x4df65u)(0xa9);
        if(!started) {S->errors++;set(&S->phase,FAILED);}
        else {S->rotations++;S->seen=0;S->energy_low=0;S->forward_recent=0;set(&S->phase,WAIT_PAPER);}
    }
    unlock_key();
}

FN("mark_copy") int mark_copy(void) {
    int result=((int (*)(void))0x4ca29u)();
    if(result) {S->errors++;if(load(&S->phase)==FINISHING)set(&S->phase,FAILED);}
    return result;
}

/* Pure pixel classifier. Unknown layouts are passed through, never interpreted
 * as a lift. Thresholds require measurement on the actual camera before enable. */
INLINE int paper(u32 *frame,u32 *edge_out,u32 *range_out) {
    /* This retail SDK frame is a packed gray plane: field 6 is its physical
       address, not a row stride. Live metadata is 96x108 in a 12288-byte block.
       Field 7 is the CPU mapping. Validate the complete pixel extent first. */
    u32 w=frame[1],h=frame[2],stride=w,bytes=frame[5];
    if(w<32||w>2048||h<32||h>2048||frame[0]!=0||
       bytes<w*h||!frame[7]) return -1;
    const u8 *pixels=(const u8 *)frame[7];
    u32 edge=0,low=255,high=0,maxstep=0;
    for(u32 y=h/3;y<h*2/3;y+=2) for(u32 x=w/16;x<w*15/16;x+=2) {
        u32 a=pixels[y*stride+x],b=pixels[y*stride+x+2];
        if(a<low)low=a;if(a>high)high=a;
        u32 difference=a>b?a-b:b-a;
        if(difference>maxstep)maxstep=difference;
        if(difference>20)edge++;
    }
    *edge_out=edge;*range_out=(maxstep<<16)|(high-low);
    u32 contrast=high-low;
    if(contrast<12)return UNCERTAIN; /* No ink is not evidence of a lift. */
    if(edge>=2 && maxstep*3>=contrast*2)return 1;
    if(maxstep*2<=contrast)return 0;
    return UNCERTAIN;
}

/* Observe before the native SDK-input gate. Copy pixels before calling the
 * original callback, which may immediately return the DMA buffer to its pool.
 * This records evidence only; it does not retain pointers or change delivery. */
FN("mark_camera") int mark_camera(u32 *event) {
    struct camera_sample *record=(void *)0;
    u32 sequence=0;
    if(event && load(&S->phase)!=OFF) {
        u32 *info=(u32 *)event[4];
        u32 number=++S->camera_frames;
        if(info && !(number&3u)) {
            u32 w=info[52],h=info[53];
            if((info[44]&~2u)==1u){u32 t=w;w=h;h=t;}
            if(w==96 && h==108 && info[0]>=w*h && info[0]<=1048576 && info[32]) {
                sequence=load(&S->camera_records);
                record=&S->camera[sequence&(CAMERA_CAPACITY-1)];
                record->serial=0;record->time=(u32)((unsigned long long (*)(void))0x4bfd5u)();
                record->phase=load(&S->phase);record->sdk_before=*(volatile u32 *)0x7c4b8u;
                record->width=w;record->height=h;record->generation=load(&S->generation);
                u32 frame[8]={0,w,h,0,0,info[0],info[20],info[32]};
                paper(frame,&record->edge,&record->range);
                const u8 *pixels=(const u8 *)info[32];
                for(u32 y=0;y<27;y++)for(u32 x=0;x<24;x++)
                    record->pixels[y*24+x]=pixels[(y*4+2)*w+x*4+2];
                observe_movement(record->pixels);
            }
        }
    }
    int result=((int (*)(u32 *))MARK_CAMERA_TRAMPOLINE)(event);
    /* The original callback has now incremented its outstanding-frame count.
     * Only now may buffered input be submitted or returned to the pool. */
    mark_handoff();
    if(record) {
        record->sdk_after=*(volatile u32 *)0x7c4b8u;
        record->pushes=S->pushes;record->rejections=S->rejections;
        record->last_push=S->last_push;record->callback_result=(u32)result;
        record->serial=sequence+1;
        set(&S->camera_records,sequence+1);
    }
    return result;
}

FN("mark_frame") int mark_frame(u32 handle,u32 index,u32 *frame) {
    if(!frame||load(&S->phase)==OFF) return original_push(handle,index,frame);
    u32 generation=load(&S->generation);
    if(S->observed!=generation) {
        S->observed=generation;S->seen=0;S->blanks=0;S->frames=0;S->count=0;
        S->rotations=0;S->errors=0;S->would_rotate=0;
#ifdef MARK_MONITOR_ONLY
        S->snapshot_bytes=0;S->snapshot_edge=0;
#endif
    }
    u32 edge=0,range=0;int contact=paper(frame,&edge,&range);
    u32 phase=load(&S->phase),number=++S->frames;
    S->width=frame[1];S->height=frame[2];S->physical_address=frame[6];S->bytes=frame[5];
#ifdef MARK_MONITOR_ONLY
    if(contact>=0 && frame[1]*frame[2]<=16384 &&
       (!S->snapshot_bytes || edge>S->snapshot_edge)) {
        S->snapshot_width=frame[1];S->snapshot_height=frame[2];
        S->snapshot_bytes=frame[1]*frame[2];S->snapshot_edge=edge;
        const u8 *pixels=(const u8 *)frame[7];
        for(u32 i=0;i<S->snapshot_bytes;i++)S->snapshot[i]=pixels[i];
    }
#endif
    if(!(number&3u)&&S->count<SAMPLE_CAPACITY) {
        u32 n=S->count++;
        S->samples[n].frame=number;S->samples[n].edge=edge;
        S->samples[n].range=range;S->samples[n].phase=phase;
    }
    if(contact<0) return original_push(handle,index,frame);
#ifdef MARK_MONITOR_ONLY
    if(contact==1) {S->seen=1;S->blanks=0;}
    else if(contact==UNCERTAIN)S->blanks=0;
    else if(S->seen&&++S->blanks==LIFT_FRAMES) {S->would_rotate++;S->seen=0;}
    return original_push(handle,index,frame);
#else
    if(phase==FINISHING) return -1; /* caller releases unsubmitted frame */
    if(phase==WAIT_PAPER) {
        if(contact!=1)return -1;
        /* Wake-up may create the pool after physical key-down. Probe when an
         * actual frame reaches us instead of preserving an early zero result. */
        if(!S->queue_capacity)S->queue_capacity=buffer_capacity();
        /* Quality selection belongs to startup even when there is too little
         * native memory to retain a frame. Don't seed the SDK on a static edge. */
        if(S->reference_energy && S->current_energy*2<S->reference_energy &&
           !S->forward_recent)return -1;
        if(S->queue_capacity) {
            S->seen++;S->blanks=0;
            S->pending_handle=handle;S->pending_index=index;
            S->pending_generation=generation;S->pending_frame=(u32)frame;
            return 0; /* Retain native buffer; hand off after caller counts it. */
        }
        S->seen=1;S->blanks=0;begin_line();
    } else if(phase==LINE) {
        if(contact==1) {if(S->seen<ARM_FRAMES)S->seen++;S->blanks=0;}
        else if(contact==UNCERTAIN)S->blanks=0;
        else {
            if(S->seen<ARM_FRAMES) {S->seen=0;S->blanks=0;}
            else if(++S->blanks>=LIFT_FRAMES) {
                set(&S->phase,FINISHING);
                int queued=((int (*)(void (*)(u32),u32))0x4c805u)(mark_rotate,generation);
                if(queued) {S->errors++;S->blanks=0;set(&S->phase,LINE);}
                else return -1;
            }
            /* Until a lift is confirmed, keep every frame. Dropping tentative
             * frames creates holes even when focus recovers without a restart. */
        }
    }
    return original_push(handle,index,frame);
#endif
}

/* Bounded binary trace, written only after the normal release has drained SDK
 * frames. Replaced at each release; no added Bluetooth packets. */
INLINE void save_trace(void) {
    char path[64];volatile u32 format[10];
    format[0]=0x64656d2f;
    format[1]=0x442f6169;
    format[2]=0x6e676169;
    format[3]=0x6974736f;
    format[4]=0x732f7363;
    format[5]=0x6f646168;
    format[6]=0x72742f77;
    format[7]=0x2d656361;
    format[8]=0x622e7525;
    format[9]=0x00006e69;
    ((int (*)(void *,const void *,u32))0x21414u)(path,(const void *)format,(load(&S->generation)>>1)&15u);
    volatile u32 mode=0x6277; /* wb */
    void *file=((void *(*)(const void *,const void *))0x20b28u)((const void *)path,(const void *)&mode);
    if(file) {
        u32 n=S->count;if(n>SAMPLE_CAPACITY)n=SAMPLE_CAPACITY;
#ifdef MARK_MONITOR_ONLY
        ((usize (*)(const void *,usize,usize,void *))0x20bd8u)(S,1,56+n*16,file);
#else
        ((usize (*)(const void *,usize,usize,void *))0x20bd8u)(S,1,60+n*16,file);
#endif
#ifdef MARK_MONITOR_ONLY
        ((usize (*)(const void *,usize,usize,void *))0x20bd8u)
            (&S->snapshot_width,1,16+S->snapshot_bytes,file);
#endif
        ((int (*)(void *))0x21478u)(file);
    }
}

INLINE void save_camera(void) {
    char path[64];volatile u32 format[10];
    /* /media/Diagnostics/shadow/camera-%u.bin */
    format[0]=0x64656d2f;format[1]=0x442f6169;format[2]=0x6e676169;
    format[3]=0x6974736f;format[4]=0x732f7363;format[5]=0x6f646168;
    format[6]=0x61632f77;format[7]=0x6172656d;format[8]=0x2e75252d;
    format[9]=0x006e6962;
    ((int (*)(void *,const void *,u32))0x21414u)(path,(const void *)format,(load(&S->generation)>>1)&15u);
    volatile u32 mode=0x6277;
    void *file=((void *(*)(const void *,const void *))0x20b28u)(path,(const void *)&mode);
    if(file) {
        u32 count=load(&S->camera_records),stored=count;
        if(stored>CAMERA_CAPACITY)stored=CAMERA_CAPACITY;
        u32 header[12]={0x314d4143,1,0x32425143,load(&S->generation),
            S->camera_frames,count,stored,sizeof(struct camera_sample),
            S->pushes,S->rejections,S->last_push,S->errors};
        ((usize (*)(const void *,usize,usize,void *))0x20bd8u)(header,1,sizeof(header),file);
        ((usize (*)(const void *,usize,usize,void *))0x20bd8u)(S->camera,1,stored*sizeof(struct camera_sample),file);
        ((int (*)(void *))0x21478u)(file);
    }
}
INLINE void save_queue(void) {
    char path[64];volatile u32 format[10];
    format[0]=0x64656d2f;format[1]=0x442f6169;format[2]=0x6e676169;
    format[3]=0x6974736f;format[4]=0x732f7363;format[5]=0x6f646168;
    format[6]=0x75712f77;format[7]=0x2d657565;format[8]=0x622e7525;format[9]=0x00006e69;
    ((int (*)(void *,const void *,u32))0x21414u)(path,(const void *)format,(load(&S->generation)>>1)&15u);
    volatile u32 mode=0x6277;
    void *file=((void *(*)(const void *,const void *))0x20b28u)(path,(const void *)&mode);
    if(file) {
        u32 header[17]={0x31464251,2,load(&S->generation),S->queue_capacity,
            S->queue_peak,S->queue_sent,S->queue_released,S->queue_errors,
            S->queue_fallbacks,(u32)S->direction,S->reference_energy,
            S->current_energy,S->moving_samples,S->energy_low,S->queue_count,S->pending_frame,
            S->pool_observed};
        ((usize (*)(const void *,usize,usize,void *))0x20bd8u)(header,1,sizeof(header),file);
        ((int (*)(void *))0x21478u)(file);
    }
}
FN("mark_up") int mark_up(u32 key,u32 context,u32 duration,u32 count) {
    u32 phase=load(&S->phase);
    if(key==0xa9u) {set(&S->phase,OFF);__atomic_fetch_add(&S->generation,1,__ATOMIC_ACQ_REL);}
    if(key==0xa9u)mark_flush(phase==WAIT_PAPER || phase==LINE);
    int result=1;
    /* A virtual key-up already owns completion during this interval. */
    if(key!=0xa9u || (phase!=FINISHING && phase!=FAILED) || held())
        result=((int (*)(u32,u32,u32,u32))0x4db7du)(key,context,duration,count);
    if(key==0xa9u){save_trace();save_camera();save_queue();}
    return result;
}

struct image {u32 width,height;u8 *pixels;};
FN("mark_image") void mark_image(struct image *source) {
#ifndef MARK_MONITOR_ONLY
    if(source && source->pixels) {
        volatile u32 directory[7];
        directory[0]=0x64656d2f;directory[1]=0x442f6169;directory[2]=0x6e676169;
        directory[3]=0x6974736f;directory[4]=0x732f7363;directory[5]=0x6f646168;
        directory[6]=0x00002f77;
#ifdef MARK_MONITOR_ONLY
        volatile u32 name[6];
        name[0]=0x6574616c;name[1]=0x6d2d7473;name[2]=0x69746c75;
        name[3]=0x656e696c;name[4]=0x706e692d;name[5]=0x00007475;
#else
        /* Keep a bounded ring of whole-line evidence outside app-managed files. */
        char name[32];volatile u32 format[2];
        format[0]=0x656e696c;format[1]=0x0075252d;
        u32 index=__atomic_fetch_add(&S->saved,1,__ATOMIC_RELAXED)&15u;
        ((int (*)(void *,const void *,u32))0x21414u)(name,(const void *)format,index);
#endif
        ((int (*)(const void *,const void *,const u8 *,u32,u32,u32))0x3a129u)
            ((const void *)directory,(const void *)name,source->pixels,source->width,source->height,10);
    }
#endif
    ((void (*)(struct image *))MARK_WORKER_TRAMPOLINE)(source);
}
