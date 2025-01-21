import numpy as np
import matplotlib.pyplot as plt 
from astropy.io import fits
import functions
import scipy.spatial as sp

from IPython import embed

def iteration_moderator(target,signal,var,geocarray,scalearray,epsilon,minsize,incidence,mode,mask=None,display=False):
    if mode=="WVT2s":
        ## WVT2s requires different iteration behavior
        ## we form bins as usual
        ## then pass through one regularization to smooth bin edges
        if mask is None:
            mask=np.full_like(signal,1)
        binlist,init_generators,init_scalelengths=next_iteration(target,signal,var,geocarray,scalearray,"VT",mask)
        ## now we save the internal bins that do not need iteration
        mask,savebins,savegeoc,othergenerators,otherscalelengths=maskbins(binlist,minsize,incidence,signal,var,target,init_generators,mask=mask)
        if np.sum(mask)==0:
            ## there is no outside bins so we just return internal bins
            print("No outside bins formed. Inside bins left uniterated.")
            return binlist,[]
        ## now iterate outside bins
        otherbinlist,diflist=iteration_func(target,signal,var,othergenerators,otherscalelengths,epsilon,mode,display,mask=mask)
        ## and combine
        binlist=savebins+otherbinlist
        return binlist,diflist
    elif mode=="VT":
        return iteration_func(target,signal,var,geocarray,scalearray,-1,mode,display,mask=mask)
    else:
        return iteration_func(target,signal,var,geocarray,scalearray,epsilon,mode,display,mask=mask)

def iteration_func(target,signal,var,geocarray,scalearray,epsilon,mode,display=False,mask=None):
    wvt=np.copy(signal)
    if mask is None:
        mask=np.full_like(signal,1)

    ## have to manually kill terminal if does not converge
    difference=2*epsilon
    diflist=[]
    repeat=True
    numit=0
    maxit=50
    iterator=0

    while repeat:
        print("another iteration")
        iterator+=1
        wvt2=np.copy(wvt)
        binlist,geocarray,scalearray=next_iteration(target,signal,var,geocarray,scalearray,mode,mask)
        wvt,ston=functions.generate_wvt3(binlist,signal*mask,var,scalearray,10,displayWVT=display)
        difference=np.sqrt(np.sum((wvt-wvt2)**2)/np.sum(var))
        print("dif",difference)

        diflist.append(difference)
        if epsilon<0:
            numit+=1
            if numit+epsilon>=0:
                repeat=False
        else:
            repeat=difference>epsilon
        if maxit<=iterator:
            repeat=False

    return binlist,diflist

def next_iteration(target,signal,var,geocarray,scalearray,mode,mask=None):
    ## generate all of the pixels to be slotted into a bin determined by the generators
    
    # unmask=np.full_like(mask,1)
    if mask is None:
        mask=np.full_like(signal,1)

    assign=np.full_like(signal,-1,dtype=int)
    viable=[]
    for g in range(len(geocarray)):
        point=(int(geocarray[g][0]),int(geocarray[g][1]))
        try:
            assign[point[0]][point[1]]=g
        except:
            print(point)
            print(geocarray[g])
            print(g)
            raise NameError("ouchie!")
        viable.append([])
        append_validate((point[0]+1,point[1]),viable[g],mask)
        append_validate((point[0]-1,point[1]),viable[g],mask)
        append_validate((point[0],point[1]+1),viable[g],mask)
        append_validate((point[0],point[1]-1),viable[g],mask)
        #print(str(int(g*100/len(geocarray)))+" percent done with init pass")
    while checkneg(assign*mask) or viabunempty(viable):
        for g in range(len(geocarray)):
            prune=True
            while prune and len(viable[g])>0:
                point=viable[g].pop(0)
                if assign[point[0]][point[1]]==g:
                    prune=True
                else:
                    prune=False
            if len(viable[g])>0:
                if assign[point[0]][point[1]]==-1:
                    assign[point[0]][point[1]]=g
                    append_validate((point[0]+1,point[1]),viable[g],mask)
                    append_validate((point[0]-1,point[1]),viable[g],mask)
                    append_validate((point[0],point[1]+1),viable[g],mask)
                    append_validate((point[0],point[1]-1),viable[g],mask)
                else:
                    if ((geocarray[g][0]-point[0])**2+(geocarray[g][1]-point[1])**2)/(scalearray[g]**2)<((geocarray[assign[point[0]][point[1]]][0]-point[0])**2+(geocarray[assign[point[0]][point[1]]][1]-point[1])**2)/(scalearray[assign[point[0]][point[1]]]**2):
                        assign[point[0]][point[1]]=g
                        append_validate((point[0]+1,point[1]),viable[g],mask)
                        append_validate((point[0]-1,point[1]),viable[g],mask)
                        append_validate((point[0],point[1]+1),viable[g],mask)
                        append_validate((point[0],point[1]-1),viable[g],mask)
                    else:
                        pass
    binlist=[ [] for _ in range(len(geocarray)) ]
    for j in range(len(assign)):
        for i in range(len(assign[0])):
            if assign[j][i]!=-1 and mask[j][i]==1:
                binlist[assign[j][i]].append((j,i))

    if mode=="CVT":
        binlist,geocarray=functions.calculate_cvt(binlist,signal,var)
        scalearray=np.full(len(geocarray),1)
    elif mode=="VT":
        binlist,geocarray,scalearray=functions.calculate_scales(target,binlist,signal,var)
        scalearray=np.full(len(geocarray),1)
    else:
        binlist,geocarray,scalearray=functions.calculate_scales(target,binlist,signal,var)
    return binlist,geocarray,scalearray
    

def checkneg(assign):
    num=np.count_nonzero(assign==-1)
    #print(num)
    if num>0:
        return True
    else:
        return False

def viabunempty(viable):
    for binn in viable:
        if len(binn)>0:
            return True
    return False

def append_validate(candidate,target,check):
    try:
        if candidate[0]<0 or candidate[0]>=len(check) or candidate[1]<0 or candidate[1]>=len(check[0]):
            raise NameError("brrr overflow bro")
        if check[candidate[0]][candidate[1]]==1:
            target.append(candidate)
    except:
        pass

def maskbins(binlist,minsize,incidence,sig,var,target,geoc,mask=None):
    ## for use in the WVT 2 stage method. Makes every bin less than cutpff outisde bin, which are iterated
    ## every bin greater than cutpff inside bin, which are not iterated
    init_SN=np.array([functions.calculate_SN(binlist[i],sig,var) for i in range(len(binlist))])

    
    ## can be modified relative to the target value
    ## density. above this, we generally would assume that there arent many negative pixels dragging down
    cutpff=1*target/minsize
    print(cutpff)
    if mask is None:
        mask=np.full_like(sig,1)
    savebins=[]
    savegeoc=[]

    basicSNsum=0
    otherSN=[]
    otherscales=[]
    othergeoc=[]
    for i in range(len(binlist)):
        #print(init_SN[i]/len(binlist[i]))
        if init_SN[i]/len(binlist[i])>=cutpff:
            savebins.append(binlist[i])
            savegeoc.append((geoc[i][0],geoc[i][1]))
            for (y,x) in binlist[i]:
                mask[y][x]=0
        else:
            otherSN.append(init_SN[i])
            otherscales.append(np.sqrt(target*len(binlist[i])/(3.14*init_SN[i])))
            othergeoc.append((geoc[i][0],geoc[i][1]))
    if len(otherSN)>1:
        removal=int((len(otherSN)-1)*incidence)+1
        otherSN=np.array(otherSN)
        otherscales=np.array(otherSN)
        othergeoc=np.array(othergeoc)
        indices=np.argsort(otherSN) 
        otherscales=otherscales[indices[removal:]]
        othergeoc=othergeoc[indices[removal:]]
    ## returns mask (1 is use, 0 is not use), the list of saved bins, the list of saved inside generators,
    ## and the outside generators and scales (for iteration)
    ## except we remove the lower some% of bins, since we expect some amount of noise so we generally want bigger bins
    return mask,savebins,savegeoc,othergeoc,otherscales