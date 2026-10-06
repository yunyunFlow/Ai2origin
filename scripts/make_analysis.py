#!/usr/bin/env python3
"""Invented analysis fixtures; independent forward equations, no measured data."""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np


def generate(out):
    out=Path(out)
    if out.exists():raise ValueError('Use a new directory; source fixtures are never overwritten')
    out.mkdir(parents=True);jobs=[];truth={}
    def table(name,headers,rows):
        with (out/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f,lineterminator='\n');w.writerow(headers)
            w.writerows([[format(float(v),'.17g') if isinstance(v,(float,np.floating)) else v for v in r] for r in rows])
    def role(column,unit):return {'column':column,'unit':unit}
    def source(file,roles,metadata=None,selection=None):
        s={'file':file,'roles':roles,'sample_id':'Invented-A','processing':'Independently assigned synthetic forward data; no measurement or digitization.','metadata':metadata or {}}
        if selection:s['selection']={'start':selection[0],'stop':selection[1]}
        return s
    def job(identifier,method,inputs,parameters):
        j={'id':identifier,'method':method,'sample_id':'Invented-A','synthetic':True,'inputs':inputs,'parameters':parameters};jobs.append(j);return j
    rates=[.0002,.0004,.0006,.0008,.001,.002];cv_rows=[];cv_inputs=[];peak_inputs=[];n=201
    for branch,sign in [('charge',1),('discharge',-1)]:
        grid=np.linspace(0,1,n)
        if sign==-1:grid=grid[::-1]
        for rate in rates:
            envelope=np.sin(np.pi*grid)**2;envelope[[0,-1]]=0
            k1=sign*(.007+.006*np.exp(-((grid-.5)/.24)**2))*envelope
            k2=sign*(.00016+.0007*np.exp(-((grid-(.65 if sign==1 else .35))/.15)**2))*envelope
            current=k1*rate+k2*math.sqrt(rate);start=len(cv_rows)
            cv_rows.extend(zip(grid,current,np.full(n,rate),[branch]*n,k1*rate,k2*math.sqrt(rate)))
            s=source('analysis-cv.csv',{'potential':role('E','V'),'current':role('I','A')},{'branch':branch,'rate_V_s':rate},[start,start+n]);cv_inputs.append(s)
            if sign==1:peak_inputs.append(s)
    table('analysis-cv.csv',['E','I','rate','branch','assigned_linear','assigned_sqrt'],cv_rows)
    job('cv','cv_dunn',cv_inputs,{'complete_cycle':True,'residual_tolerance':.02,'fit_space':'normalized','display_rates_V_s':[.0002,.001]})
    job('peaks','cv_peaks',peak_inputs,{'window_V':[.45,.85],'polarity':'anodic'})
    # Separate nonfaradaic control, not a fitted background inferred from redox CV.
    control_rows=[];control_inputs=[];cn=21
    for branch,sign in [('anodic',1),('cathodic',-1)]:
        common=np.linspace(.3,.5,cn);grid=common if sign==1 else common[::-1]
        for rate in rates:
            start=len(control_rows);control_rows.extend(zip(grid,np.full(cn,sign*.018*rate)))
            control_inputs.append(source('analysis-control.csv',{'potential':role('E','V'),'current':role('I','A')},{'branch':branch,'rate_V_s':rate},[start,start+cn]))
    table('analysis-control.csv',['E','I'],control_rows)
    job('cdl','cv_cdl',control_inputs,{'paired_cathodic_reversal':True,'sample_potential_V':.4,'linearity_tolerance':.01,
         'conditions':{'nonfaradaic_window':True,'sampling_checked':True,'ohmic_drop_assessed':True,'repeatability_checked':True}})
    truth['assigned_control_capacitance_F']=.018
    # Independent finite-slab solution; estimator never sees assigned D.
    gitt_rows=[];gitt_inputs=[];length=25e-6;current=9e-6;nominal_q=1.08;tau=120.;ocv_slope=.08
    for i,D in enumerate([1e-14,2e-14,4e-14]):
        t=np.arange(0,tau+1);flux=current*length/nominal_q;terms=np.arange(1,6001,dtype=float)
        beta=D*t/length**2
        summed=np.sum(np.exp(-np.pi**2*terms[:,None]**2*beta[None,:])/terms[:,None]**2,axis=0)
        surface=flux*length/D*(beta+1/3-2/np.pi**2*summed);surface[0]=0
        pre=1.2+i*.035;post=pre+ocv_slope*current*tau/nominal_q
        e=pre+current*40+ocv_slope*surface;start=len(gitt_rows);gitt_rows.extend(zip(t,e,np.full(len(t),current)))
        meta={'pulse_id':'P'+str(i+1),'coordinate':20+i*30,'coordinate_unit':'%', 'pulse_tau_s':tau,'pre_eq':pre,'post_eq':post,
              'length_m':length,'equilibrium_confirmed':True,'transient_excluded':True,
              'physical_conditions':{'small_perturbation':True,'diffusion_dominance':True,'effective_geometry_verified':True}}
        gitt_inputs.append(source('analysis-gitt.csv',{'time':role('t','s'),'potential':role('E','V'),'current':role('I','A')},meta,[start,start+len(t)]))
    table('analysis-gitt.csv',['t','E','I'],gitt_rows)
    job('gitt','gitt',gitt_inputs,{'fit_window_s':[10,40],'short_time_limit':.01,'r2_min':.99,'current_constancy_tolerance':1e-6,'coordinate_axis':{'label':'Assigned SOC','unit':'%'}})
    truth['gitt_D_m2_s']=[1e-14,2e-14,4e-14]
    # Monotonic branches and known integral, derivative has no numerical smoothing.
    voltage=np.linspace(.9,1.9,101);charge=.36*((voltage-.9)+.12*np.tanh((voltage-1.4)/.08)-.12*np.tanh((.9-1.4)/.08))
    table('analysis-gcd.csv',['E','Q'],zip(voltage,charge))
    gcd=source('analysis-gcd.csv',{'potential':role('E','V'),'charge':role('Q','C')})
    job('ica','ica',[gcd],{'Q_convention':'branch_capacity'})
    # Anode-positive current and a declared reference offset; known additional iR.
    j=np.geomspace(1e-6,.005,61);eta=.06*np.log10(j/1e-8);area=1.;ru=5.;raw=eta+j*area*ru
    table('analysis-lsv.csv',['E','j'],zip(raw,j))
    lsv=source('analysis-lsv.csv',{'potential':role('E','V'),'current':role('j','A/cm2')})
    job('tafel','tafel',[lsv],{'prepare':{'current_sign':'anodic_positive','area_cm2':area,'ir':{'Ru_ohm':ru,'input_compensation':'none','prior_fraction':0,'residual_fraction':1},
        'reference':{'mode':'direct_RHE','offset_V':0,'provenance':'Assigned synthetic RHE potential'},'equilibrium_potential_RHE_V':0},
        'fit':{'window':{'kind':'indices','indices':list(range(61))},'polarity':'anodic','log_reference_value':1,'log_reference_unit':'A/cm2',
               'conditions':{'steady_state':True,'charging_negligible':True,'transport_negligible':True,'uniform_access':True,'single_kinetic_regime':True}}})
    truth['tafel_mV_per_dec']=60.
    # Direct complex forward equation, independent of the fitting implementation.
    f=np.geomspace(1e3,1e-6,71);eis_inputs=[]
    for i in range(3):
        z=3+(18+6*i)/(1+2j*np.pi*f*.02)+(40-5*i)/(1+2j*np.pi*f*200)
        name='analysis-eis-'+str(i)+'.csv';table(name,['f','real','imag'],zip(f,z.real,z.imag))
        eis_inputs.append(source(name,{'frequency':role('f','Hz'),'real':role('real','ohm'),'imaginary':role('imag','ohm')},{'imaginary_convention':'Zimag'}))
    job('eis','eis_rc',[eis_inputs[0]],{'n_rc':2,'initial_guesses':[[2,10,.01,50,100],[5,35,.06,20,800]],'bounds':[[.01,.01,1e-5,.01,1],[100,1000,10,1000,10000]],'weighting':'modulus'})
    tau_grid=np.geomspace(1e-3,1e5,65)
    job('drt','drt',eis_inputs,{'tau':tau_grid.tolist(),'lambdas':[1e-5,1e-4,1e-3],'selected_lambda':1e-4,'order':2,'weighting':'modulus',
        'condition_axis':{'label':'Assigned condition','unit':'a.u.','values':[0,1,2]}})
    truth['eis_Rs_R1_tau1_R2_tau2']=[3,18,.02,40,200]
    # Gaussian normalized whole-line areas, no chemical population inference.
    for identifier,profile,x,centers,widths,areas,unit in [('raman','raman',np.linspace(1100,1800,351),[1350,1580],[75,48],[900,1200],'a.u.'),
         ('ftir','ftir',np.linspace(2800,3800,301),[3220,3490],[150,110],[35,45],'absorbance'),
         ('xps','xps',np.linspace(278,294,321),[284.4,286.2,288.6],[.9,1.1,1.],[2200,900,600],'counts')]:
        mid=(x[0]+x[-1])/2;baseline=(18+.015*(x-mid)) if profile=='raman' else (.012+.000005*(x-mid)) if profile=='ftir' else (30+.6*(x-mid))
        y=baseline.copy()
        for c,w,a in zip(centers,widths,areas):y+=a/w*math.sqrt(4*math.log(2)/math.pi)*np.exp(-4*math.log(2)*((x-c)/w)**2)
        name='analysis-'+identifier+'.csv';table(name,['x','y'],zip(x,y))
        meta={'energy_type':'binding','scan_type':'high_resolution','background_state':'none','energy_calibration':'Assigned binding-energy coordinates; no shift'} if profile=='xps' else {}
        inp=source(name,{'coordinate':role('x','eV' if profile=='xps' else 'cm^-1'),'intensity':role('y',unit)},meta)
        job(identifier,'spectra_peaks',[inp],{'profile':profile,'centers':centers,'width_bounds':[[w*.4,w*2] for w in widths],
            'baseline':{'kind':'joint_linear'},'kind':'gaussian','starts':5})
        truth[identifier+'_areas']=areas
    # Explicit known correction artifacts; fit-window excludes the redox signal.
    ee=np.linspace(0,1,201);background=np.full(len(ee),1e-6)
    redox=np.where(ee>.5,3e-6*np.sin(2*np.pi*(ee-.5))**2,0.)
    tail=1e-5*np.exp(-ee/.15);ii=background+tail+redox
    table('analysis-correction.csv',['E','I','background'],zip(ee+ii*20,ii,background))
    job('correction','cv_correct',[source('analysis-correction.csv',{'potential':role('E','V'),'current':role('I','A'),'background':role('background','A')})],
        {'ir':{'resistance_ohm':20,'already_compensated_fraction':0,'resistance_source':'Independently assigned toy series resistance'},
         'tail':{'branch_direction':1,'fit_window_V':[.01,.15],'baseline_current':1e-6,'amplitude_bounds':[5e-6,2e-5],
                 'decay_scale_bounds_V':[.05,.3],'model_source':'Assigned single exponential artifact, isolated fit window','relative_rmse_limit':.001},
         'background':{'role':'background','source':'Independent assigned background column'},
         'alignment':{'grid_V':np.linspace(.05,.95,101).tolist(),'interpolation':'piecewise_linear'}})
    truth['correction_redox_A']=redox.tolist()
    qq=np.linspace(0,.36,101);qd=qq*.92
    table('analysis-cycle.csv',['Qc','Ec','Qd','Ed'],zip(qq,1.4+.4*qq/qq[-1],qd,1.6-.4*qd/qd[-1]))
    job('cycle','cycle_efficiency',[source('analysis-cycle.csv',{'charge':role('Qc','C'),'potential':role('Ec','V')},{'branch':'charge'}),
        source('analysis-cycle.csv',{'charge':role('Qd','C'),'potential':role('Ed','V')},{'branch':'discharge'})],
        {'Q_convention':'branch_capacity','complete_branches':True,'voltage_basis':'cell_terminal'})
    truth['cycle_CE']=.92
    be=np.linspace(280,300,401);sigma=1.2/math.sqrt(8*math.log(2))
    yd=30+sum(a/(sigma*math.sqrt(2*math.pi))*np.exp(-.5*((be-c)/sigma)**2) for c,a in [(285.2,800),(291.2,400)])
    table('analysis-doublet.csv',['kinetic','counts'],zip(1486.6-4-be,yd))
    meta={'energy_type':'kinetic','scan_type':'high_resolution','background_state':'none','energy_calibration':'Assigned hnu and spectrometer work-function convention'}
    job('doublet','spectra_doublet',[source('analysis-doublet.csv',{'coordinate':role('kinetic','eV'),'intensity':role('counts','counts')},meta)],
        {'profile':'xps','energy':{'photon_energy_eV':1486.6,'work_function_eV':4},'center':285.2,'split_eV':6,'area_ratio':2,
         'width_bounds':[.5,2],'baseline':{'kind':'joint_linear'},'kind':'gaussian'})
    be=np.linspace(276,296,801);yy=np.zeros(len(be));cdf=np.zeros(len(be))
    for c,a in [(283,1000),(287,500)]:
        sigma=1/math.sqrt(8*math.log(2));yy+=a/(sigma*math.sqrt(2*math.pi))*np.exp(-.5*((be-c)/sigma)**2)
        cdf+=a*.5*(1+np.array([math.erf((x-c)/(sigma*math.sqrt(2))) for x in be]))
    bg=25+80*(cdf-cdf[0])/(cdf[-1]-cdf[0]);table('analysis-shirley.csv',['BE','counts'],zip(be,yy+bg))
    job('shirley','spectra_peaks',[source('analysis-shirley.csv',{'coordinate':role('BE','eV'),'intensity':role('counts','counts')},
        {'energy_type':'binding','scan_type':'high_resolution','background_state':'none','energy_calibration':'Assigned binding-energy toy coordinates'})],
        {'profile':'xps','centers':[283,287],'width_bounds':[[.5,2],[.5,2]],'kind':'gaussian',
         'baseline':{'kind':'shirley','endpoints':[25,105],'source':'Independently assigned toy endpoint backgrounds','tolerance':1e-10}})
    (out/'analysis.json').write_text(json.dumps({'schema_version':1,'jobs':jobs},indent=2)+'\n')
    (out/'truth.json').write_text(json.dumps(truth,indent=2)+'\n')
    return {'jobs':len(jobs),'all_data':'SYNTHETIC_INDEPENDENT_FORWARD_EQUATIONS'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();print(json.dumps(generate(a.out)))
