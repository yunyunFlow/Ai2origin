#!/usr/bin/env python3
"""Generate article-oriented toy inputs, not measured data or engine results."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np


def make_templates(target):
    if target.exists() or target.is_symlink():
        raise FileExistsError("Use a new template directory")
    target.mkdir(parents=True)

    def table(name, columns):
        with (target / name).open("x", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows([[format(float(v), ".17g") for v in row] for row in zip(*columns.values(), strict=True)])

    def plot(identity, csv_name, x, series, xlabel, ylabel, **options):
        return dict(id=identity, kind=options.pop("kind", "line"), csv=csv_name, x=x, series=series,
                    synthetic=True, title="", labels={"x": xlabel, "y": ylabel}, **options)

    def series(column, label, **options):
        return dict(column=column, label=label, **options)

    phase = np.linspace(0, 2*np.pi, 129)
    potential = 0.5 - 0.5*np.cos(phase)
    current = 0.4*np.sin(phase) + 0.22*np.sin(2*phase)
    capacity = 100*(1-np.cos(phase))
    voltage = 1.05+0.4*capacity/200+0.12*np.sin(phase)
    cycles = np.arange(1, 130)
    zreal, zimag = 3+12*(1-np.cos(np.linspace(0, np.pi, 129))), 12*np.sin(np.linspace(0, np.pi, 129))
    table("electrochem.csv", dict(potential=potential, current_a=current, current_b=0.8*current,
                                 capacity=capacity, voltage=voltage, cycle=cycles,
                                 retention=100-0.035*cycles, zreal=zreal, znegimag=zimag))
    electrochem = [
        plot("cv", "electrochem.csv", "potential", [series("current_a", "A"), series("current_b", "B")],
             "Potential (V)", "Current (mA)", connect_order="acquisition"),
        plot("gcd", "electrochem.csv", "capacity", [series("voltage", "Toy cycle")],
             "Capacity (mAh/g)", "Voltage (V)", connect_order="acquisition"),
        plot("cycling", "electrochem.csv", "cycle", [series("retention", "Toy retention")],
             "Cycle", "Retention (percent)"),
        plot("nyquist", "electrochem.csv", "zreal", [series("znegimag", "Toy arc")],
             "Z real (ohm)", "-Z imaginary (ohm)", connect_order="acquisition", kind="line_symbol",
             x_range=[0,30], y_range=[0,30], x_tick_step=5, y_tick_step=5, equal_xy=True)
    ]
    # Use moderate marker sizes for dense native Nyquist points.
    t = np.linspace(500, 1800, 201)
    a = 0.08+np.exp(-((t-850)/45)**2)+0.65*np.exp(-((t-1320)/65)**2)
    b = 0.06+0.85*np.exp(-((t-880)/50)**2)+0.8*np.exp(-((t-1290)/70)**2)
    c = 0.08+0.75*np.exp(-((t-915)/55)**2)+np.exp(-((t-1255)/75)**2)
    angle = np.linspace(10, 80, len(t))
    diffraction = 0.02+sum(amp*np.exp(-((angle-position)/0.45)**2) for position,amp in [(21,0.8),(36,1.0),(59,0.65)])
    table("characterization.csv", dict(wavenumber=t, a=a, b=b, c=c, angle=angle, intensity=diffraction))
    characterization = [
        plot("spectra", "characterization.csv", "wavenumber", [series("a", "A"), series("b", "B")],
             "Wavenumber (1/cm)", "Intensity (a.u.)", x_tick_step=500),
        plot("stack", "characterization.csv", "wavenumber", [series("a", "A"), series("b", "B", offset=1.3), series("c", "C", offset=2.6)],
             "Wavenumber (1/cm)", "Intensity + offset (a.u.)", x_tick_step=500),
        plot("diffraction", "characterization.csv", "angle", [series("intensity", "Toy pattern")],
             "2θ (degree)", "Intensity (a.u.)")
    ]
    q = np.linspace(0, 1, 7)
    table("path.csv", dict(coordinate=q, energy_a=0.55*np.sin(np.pi*q)**2+0.04*q,
                           energy_b=0.38*np.sin(np.pi*q)**2-0.05*q))
    time = np.linspace(0, 10, 121)
    radius = np.linspace(0.1, 8, len(time))
    energy = np.linspace(-6, 6, len(time))
    rdf = 1+2.5*np.exp(-((radius-2.1)/0.22)**2)+0.7*np.exp(-((radius-4.2)/0.6)**2)
    dos = np.exp(-((energy+2)/0.9)**2)+0.65*np.exp(-((energy-2.4)/1.1)**2)
    table("dft-md.csv", dict(time=time, msd=0.6*time+0.08*(1-np.exp(-time)), radius=radius, rdf=rdf, energy=energy, dos=dos))
    methods = [
        plot("migration", "path.csv", "coordinate", [series("energy_a", "A"), series("energy_b", "B")],
             "Path coordinate", "Relative energy (eV)", kind="line_symbol"),
        plot("dos", "dft-md.csv", "energy", [series("dos", "Toy DOS")],
             "Energy - reference (eV)", "DOS (states/eV)"),
        plot("rdf", "dft-md.csv", "radius", [series("rdf", "Toy RDF")], "r (Å)", "g(r)"),
        plot("msd", "dft-md.csv", "time", [series("msd", "Toy MSD")], "Time (ps)", "MSD (Å²)")
    ]
    x = np.linspace(-2, 2, 36)
    y = 0.7*x+0.12+np.random.default_rng(1729).normal(0, 0.25, len(x))
    design = np.column_stack([x, np.ones_like(x)])
    fitted = design @ np.linalg.lstsq(design, y, rcond=None)[0]
    table("analysis.csv", dict(x=x, y=y, fitted=fitted, residual=y-fitted, zero=np.zeros_like(x)))
    analysis = [
        plot("association", "analysis.csv", "x", [series("y", "Observations"), series("fitted", "OLS", kind="line")], "Descriptor (a.u.)", "Response (a.u.)", kind="scatter"),
        plot("residual", "analysis.csv", "x", [series("residual", "Residuals"), series("zero", "Zero", kind="line")], "Descriptor (a.u.)", "OLS residual (a.u.)", kind="scatter")
    ]
    # Additional independent toy functions: none read literature/source data.
    pulse_t = np.linspace(0, 1200, 241)
    phase_t = pulse_t % 200
    pulse = np.where(phase_t < 30, 0.04*(1-np.exp(-phase_t/12))+0.025, 0.037*np.exp(-(phase_t-30)/45))
    gitt_v = 0.8 + 0.00025*pulse_t + pulse
    gcd_t = np.linspace(0, 1000, 201)
    gcd_v = np.where(gcd_t <= 500, 0.8+0.0016*gcd_t, 1.6-0.0016*(gcd_t-500))
    table("pulses.csv", dict(time=pulse_t, voltage=gitt_v, current=np.where(phase_t<30,1,0)))
    table("gcd-time.csv", dict(time=gcd_t, voltage_a=gcd_v, voltage_b=0.8+0.9*(gcd_v-0.8)))
    table("performance.csv", dict(cycle=cycles, capacity_a=150-0.06*cycles, capacity_b=140-0.09*cycles,
          ce_a=99.4+0.3*(1-np.exp(-cycles/12)), ce_b=99.1+0.4*(1-np.exp(-cycles/15))))
    rate_cycle=np.arange(1,25)
    table("rate.csv", dict(cycle=rate_cycle, capacity=np.repeat([150,136,110,85,108,134],4)))
    log_f=np.linspace(-2,5,121)
    omega=2*np.pi*10**log_f
    impedance=3+24/(1+1j*omega*0.01)
    table("bode.csv", dict(frequency=10**log_f, log_frequency=log_f, magnitude=np.abs(impedance), phase=np.angle(impedance,deg=True)))
    extra_echem=[
        plot("gcd-time","gcd-time.csv","time",[series("voltage_a","A"),series("voltage_b","B")],"Toy time (s)","Toy voltage (V)"),
        plot("gitt","pulses.csv","time",[series("voltage","Toy pulses")],"Toy time (s)","Toy voltage (V)"),
        plot("cycle-capacity","performance.csv","cycle",[series("capacity_a","A"),series("capacity_b","B")],"Toy cycle","Toy capacity (mAh/g)"),
        plot("coulombic","performance.csv","cycle",[series("ce_a","A"),series("ce_b","B")],"Toy cycle","Toy CE (percent)"),
        plot("rate","rate.csv","cycle",[series("capacity","Toy steps")],"Toy cycle","Toy capacity (mAh/g)",kind="line_symbol"),
        plot("bode-magnitude","bode.csv","log_frequency",[series("magnitude","Toy magnitude")],"log10 toy f (Hz)","Toy |Z| (ohm)"),
        plot("bode-phase","bode.csv","log_frequency",[series("phase","Toy phase")],"log10 toy f (Hz)","Toy phase (degree)"),
    ]
    log_tau=np.linspace(-3,5,81)
    gamma_a=0.8*np.exp(-((log_tau+2.4)/0.3)**2)+0.5*np.exp(-((log_tau-0.2)/0.45)**2)
    gamma_b=0.6*np.exp(-((log_tau+2.0)/0.35)**2)+0.7*np.exp(-((log_tau-0.5)/0.5)**2)
    table("drt.csv",dict(tau=10**log_tau,log_tau=log_tau,a=gamma_a,b=gamma_b))
    map_rows=[(x,c,0.85*np.exp(-((x+2.5-0.08*c)/0.35)**2)+0.55*np.exp(-((x-0.1-0.03*c)/0.5)**2)) for c in range(1,10) for x in log_tau]
    table("drt-map.csv",dict(toy_tau=[10**r[0] for r in map_rows],toy_condition=[r[1] for r in map_rows],toy_gamma=[r[2] for r in map_rows]))
    drt=[
        plot("drt","drt.csv","tau",[series("a","A"),series("b","B")],"Relaxation time, τ (s)","γ(τ) (a.u.)",x_scale="log10",x_range=[1e-3,1e5]),
        plot("drt-stack","drt.csv","tau",[series("a","A"),series("b","B",offset=1)],"Relaxation time, τ (s)","γ(τ) + offset (a.u.)",x_scale="log10",x_range=[1e-3,1e5]),
        dict(id="drt-map",kind="heatmap",csv="drt-map.csv",x="toy_tau",y="toy_condition",z="toy_gamma",synthetic=True,
             title="Synthetic DRT map",labels={"x":"log10 toy τ (s)","y":"Toy condition index","color":"Toy gamma (a.u.)"},
             color_range=[0,1],center=0.5,color_levels=256,cmap=["#2166AC","#F7F7F7","#B2182B"],interpolation={"method":"bilinear","factor":2}),
    ]
    strain=np.linspace(0,100,161)
    temperature=np.linspace(25,600,181)
    reaction_t=np.linspace(0,120,101)
    epoch=np.arange(1,102)
    table("mechanics.csv",dict(strain=strain,stress_a=0.04*strain+0.0005*strain**2,stress_b=0.03*strain+0.0003*strain**2))
    table("thermal.csv",dict(temperature=temperature,mass_a=100-15/(1+np.exp(-(temperature-150)/12))-60/(1+np.exp(-(temperature-390)/18)),
          mass_b=100-10/(1+np.exp(-(temperature-180)/14))-65/(1+np.exp(-(temperature-420)/20)),
          flow_a=-2*np.exp(-((temperature-160)/18)**2)+3*np.exp(-((temperature-410)/25)**2),flow_b=-1.5*np.exp(-((temperature-185)/22)**2)+2.5*np.exp(-((temperature-440)/28)**2)))
    table("kinetics.csv",dict(time=reaction_t,a=100*(1-np.exp(-reaction_t/30)),b=100*(1-np.exp(-reaction_t/45))))
    table("learning.csv",dict(epoch=epoch,train=0.1+0.9*np.exp(-epoch/20),validation=0.18+0.85*np.exp(-epoch/25)+0.002*np.maximum(epoch-65,0)))
    other=[
        plot("stress-strain","mechanics.csv","strain",[series("stress_a","A"),series("stress_b","B")],"Toy strain (percent)","Toy stress (MPa)"),
        plot("tga","thermal.csv","temperature",[series("mass_a","A"),series("mass_b","B")],"Toy temperature (°C)","Toy mass remaining (percent)"),
        plot("dsc","thermal.csv","temperature",[series("flow_a","A"),series("flow_b","B")],"Toy temperature (°C)","Toy heat flow (mW)"),
        plot("kinetics","kinetics.csv","time",[series("a","A"),series("b","B")],"Toy time (min)","Toy conversion (percent)"),
        plot("learning","learning.csv","epoch",[series("train","Train"),series("validation","Validation")],"Toy epoch","Toy loss (a.u.)"),
    ]
    # Cross-domain demonstration functions, never digitized article data.
    field=np.concatenate([np.linspace(-2,2,121),np.linspace(2,-2,121)])
    branch=np.r_[np.ones(121),-np.ones(121)]
    table('magnetism.csv',dict(field=field,magnetization_a=1.2*np.tanh((field-.12*branch)/.22),magnetization_b=.9*np.tanh((field-.07*branch)/.30)))
    temp=np.linspace(10,350,171)
    table('susceptibility.csv',dict(temperature=temp,a=.12/(temp+20)+.0002,b=.09/(temp+35)+.0002))
    wavelength=np.linspace(250,800,276)
    table('optics.csv',dict(wavelength=wavelength,absorbance_a=.08+1.1*np.exp(-((wavelength-355)/32)**2),absorbance_b=.06+.85*np.exp(-((wavelength-380)/40)**2),pl_a=np.exp(-((wavelength-510)/35)**2),pl_b=.8*np.exp(-((wavelength-545)/42)**2)))
    decay_t=np.linspace(0,50,101)
    table('decay.csv',dict(time=decay_t,a=.8*np.exp(-decay_t/4)+.2*np.exp(-decay_t/15),b=np.exp(-decay_t/9)))
    concentration=np.logspace(-3,3,121)
    table('dose.csv',dict(concentration=concentration,a=100/(1+(concentration/2)**1.2),b=100/(1+(concentration/8)**1.1)))
    hours=np.linspace(0,24,97)
    table('growth.csv',dict(time=hours,a=.05+1.4/(1+np.exp(-(hours-10)/1.8)),b=.05+1.1/(1+np.exp(-(hours-13)/2.1))))
    substrate=np.linspace(0,10,61)
    table('enzyme.csv',dict(substrate=substrate,a=1.5*substrate/(2+substrate),b=1.1*substrate/(3+substrate)))
    domains=[
        plot('hysteresis','magnetism.csv','field',[series('magnetization_a','A'),series('magnetization_b','B')],'μ0H (T)','Magnetization (emu g^-1)',connect_order='acquisition',x_range=[-2,2],y_range=[-1.5,1.5],x_tick_step=1,y_tick_step=.5),
        plot('susceptibility','susceptibility.csv','temperature',[series('a','A'),series('b','B')],'Temperature (K)','Susceptibility (a.u.)'),
        plot('uvvis','optics.csv','wavelength',[series('absorbance_a','A'),series('absorbance_b','B')],'Wavelength (nm)','Absorbance (a.u.)',x_tick_step=100,y_range=[0,1.6]),
        plot('photoluminescence','optics.csv','wavelength',[series('pl_a','A'),series('pl_b','B')],'Wavelength (nm)','PL intensity (a.u.)',x_tick_step=100,y_range=[0,1.4]),
        plot('fluorescence-decay','decay.csv','time',[series('a','A'),series('b','B')],'Time (ns)','Intensity (a.u.)'),
        plot('dose-response','dose.csv','concentration',[series('a','A'),series('b','B')],'Concentration (μM)','Viability (percent)',x_scale='log10',x_range=[1e-3,1e3],y_range=[0,130]),
        plot('growth','growth.csv','time',[series('a','A'),series('b','B')],'Time (h)','OD600 (a.u.)',y_range=[0,2],x_tick_step=5),
        plot('enzyme-kinetics','enzyme.csv','substrate',[series('a','A'),series('b','B')],'Substrate (mM)','Initial rate (μmol/min)',y_range=[0,1.8]),
    ]
    all_plots = []
    captions = {
        "cv": "Synthetic A/B current-potential loops, 129 ordered samples each, V and mA. Acquisition order and turning points retained; voltage reference is arbitrary. No scan-rate, kinetic or capacitance inference.",
        "gcd": "Synthetic charge/discharge display loop, 129 ordered samples, capacity in mAh/g and voltage in V. Capacity is a toy mass-specific quantity; no experimental active mass, current or efficiency is implied.",
        "cycling": "Synthetic retention for cycles 1-129, in percent. One assigned curve, no replicate uncertainty or lifetime extrapolation.",
        "nyquist": "Synthetic impedance arc, 129 ordered samples, real Z and negative imaginary Z in ohm. Equal physical scale per ohm, major ticks 5 ohm. No circuit fit or charge-transfer interpretation.",
        "spectra": "Synthetic A/B spectra, 201 samples from 500 to 1800 inverse cm, arbitrary intensity. Assigned peak shapes; no baseline correction, normalization, deconvolution or chemical assignment.",
        "stack": "Synthetic A/B/C spectra, 201 samples each. Display offsets 0, 1.3 and 2.6 arbitrary intensity units; raw values retained separately. No normalization or chemical assignment.",
        "diffraction": "Synthetic diffraction-like profile, 201 samples from 10 to 80 degrees in 2 theta, arbitrary intensity. Assigned peaks; no phase identification or instrument broadening model.",
        "migration": "Two synthetic seven-point energy paths in eV, relative to each path's first point. Lines connect stored images without fitting. Endpoint tilt retained; no converged NEB or barrier prediction.",
        "dos": "Synthetic DOS-shaped function, 121 samples, energy relative to an arbitrary reference in eV and toy states/eV. No electronic structure calculation, occupation or integrated state-count validation.",
        "rdf": "Synthetic g(r)-shaped function, 121 samples, r in angstrom and dimensionless g(r). No trajectory, atom selection, coordination-number or normalization validation.",
        "msd": "Synthetic MSD-shaped curve, 121 samples from 0 to 10 ps, angstrom squared. No trajectory, PBC unwrapping, statistical blocks or diffusion fit.",
        "association": "Synthetic descriptor-response scatter, 36 assigned observations in arbitrary units, RNG seed 1729. Displayed OLS values are stored predictions from an unweighted line with intercept. No causal or out-of-sample claim.",
        "residual": "Residuals for the same 36 synthetic OLS observations, observed minus stored fitted response in arbitrary units, with explicit zero line. No independence, homoscedasticity or model adequacy claim.",
    }
    captions.update({
        "gcd-time":"Invented triangular charge/discharge-time profiles A/B, 201 samples in seconds and volts. Arbitrary voltage reference; no measured capacity or cycling efficiency.",
        "gitt":"Invented pulse/rest voltage trace, 241 samples, 30-second toy pulses within 200-second periods; current stored separately. No experimental GITT, iR correction, diffusion fit or diffusion coefficient.",
        "cycle-capacity":"Invented A/B mass-specific capacity histories over 129 toy cycles. No experiment, active-mass measurement, error estimate or extrapolation.",
        "coulombic":"Invented A/B CE-shaped curves over 129 toy cycles, percent. Values assigned directly, not calculated from measured charge/discharge integrals.",
        "rate":"Invented four-cycle blocks with assigned capacity steps 150/136/110/85/108/134 mAh/g. Toy rate schedule 1/2/5/10/5/2; no experimental rate-performance conclusion.",
        "bode-magnitude":"Toy magnitude from Z=3+24/(1+i*2*pi*f*0.01), 121 assigned frequencies. Horizontal coordinates store log10(f/Hz) explicitly; no log-axis adapter, circuit fit or measured EIS.",
        "bode-phase":"Toy phase in degrees from the same assigned RC expression, 121 samples. log10(f/Hz) is stored explicitly; no phase inversion or experimental validation.",
        "drt":"Invented A/B Gaussian gamma-shaped curves, 61 log10(tau/s) coordinates. No inverse EIS, regularization, integrated resistance or process assignment; independent of toy Nyquist/Bode.",
        "drt-stack":"Same invented A/B gamma curves with display offsets 0/1 a.u.; original values retained. No EIS inversion or physical process assignment.",
        "drt-map":"Invented Gaussian peaks on 9 toy conditions and 61 log10(tau/s) nodes. Bilinear factor 2 gives 17x121 display nodes, 256 blue-white-red levels, range 0-1 a.u.; white=0.5, not zero. No measured DRT, SOC or time series.",
        "stress-strain":"Invented polynomial A/B stress-strain curves, 161 samples, percent and MPa. No specimen, modulus fit, fracture or toughness measurement.",
        "tga":"Invented logistic A/B mass-loss curves, 181 temperatures in Celsius. No specimen, heating rate, atmosphere or decomposition assignment.",
        "dsc":"Invented signed Gaussian A/B heat-flow features, 181 temperatures in Celsius and mW. Negative down, positive up; no experimental endotherm convention, mass normalization or enthalpy integration.",
        "kinetics":"Invented exponential A/B conversion-time curves, 101 points in minutes and percent. No experimental reaction, rate fit or mechanism.",
        "learning":"Invented training/validation loss functions over 101 epochs. No trained model, dataset split, predictive performance or run is claimed.",
    })
    captions['drt']='Invented A/B gamma curves: 81 positive τ nodes from 10^-3 to 10^5 s, true log10 X axis. No EIS inversion, regularization or process assignment.'
    captions['drt-stack']=captions['drt']+' Display offsets 0/1 a.u.; raw values retained.'
    captions['drt-map']='Invented 9x81 condition/τ nodes. Display-only bilinear interpolation in log10(τ),condition, factor 8: 65x641 display nodes, 256 blue-white-red levels, [0,1], white=0.5. Raw nodes retained; no new observations, denoising, physical resolution or EIS inversion.'
    captions['migration']+=' Seven original nodes shown as points; shape-preserving PCHIP (factor 16) is display-only, not extra images, fits or stationary points. Barriers use source nodes.'
    for spec in domains:
        captions[spec['id']]='Invented A/B '+spec['id']+' demonstration functions; units and acquisition order as labeled. No specimen, measurement, parameter fit, physical process or biological mechanism is inferred.'
        spec['kind']='line_symbol' if spec['id'] in ('susceptibility','fluorescence-decay','dose-response','growth','enzyme-kinetics') else 'line'
    captions['nyquist']='Invented 129-point impedance arc. Both axes span 0–30 Ω, major ticks 5 Ω and equal physical scale; square frame. No circuit fit or charge-transfer interpretation.'
    for name, plots in (("electrochem", electrochem+extra_echem), ("characterization", characterization), ("dft-md", methods), ("analysis", analysis), ("drt",drt), ("other",other),('domains',domains)):
        for spec in plots:
            spec['title']=''
            if spec['id']=='stack': spec['y_range']=[0,5]
            if spec['id']=='rate': spec['x_tick_step']=5
            if spec['id'] in ('cycle-capacity','bode-magnitude'): spec['y_tick_step']=5
            spec['labels']={k:v.replace('Toy ','').replace('toy ','').replace('mAh/g','mAh g^-1').replace('1/cm','cm^-1').replace('degree','°').replace('ohm','Ω').replace('Z real','Z′').replace('-Z imaginary','−Z″') for k,v in spec['labels'].items()}
            for s in spec.get('series',[]): s['label']=s['label'].replace('Toy ','')
            if spec['id'] in {'cycling','cycle-capacity','coulombic','rate','msd','kinetics','learning','stress-strain','drt','drt-stack'}:spec['kind']='line_symbol'
            if spec['id']=='migration':spec.update(connection='pchip',connection_factor=16)
            if spec['id'].startswith('drt'):
                spec['labels']['x']='Relaxation time, τ (s)'
            if spec['id']=='drt-map':
                spec.update(x_scale='log10',x_range=[1e-3,1e5],interpolation={'method':'bilinear','factor':8})
                spec['labels'].update(y='Condition index (synthetic)',color='γ(τ) (a.u.)')
            if spec['id'].startswith('bode-'):
                spec.update(x='frequency',x_scale='log10',x_range=[1e-2,1e5])
                spec['labels']['x']='Frequency (Hz)'
                captions[spec['id']]='Invented complex-impedance function at 121 actual positive frequency nodes; true log10 frequency axis, not a fit. Independent of toy Nyquist/DRT.'
            spec["caption"] = captions[spec["id"]]
        config = {"schema_version": 1, "style": {"marker": {"size_pt": 2.5}}, "plots": plots}
        (target / (name + ".json")).write_text(json.dumps(config, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        all_plots.extend(plots)
    (target / "paper.json").write_text(json.dumps({"schema_version": 1, "style": {"marker": {"size_pt": 2.5}}, "plots": all_plots}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    make_templates(parser.parse_args().out)
