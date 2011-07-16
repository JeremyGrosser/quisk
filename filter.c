#include <Python.h>
#include <stdlib.h>
#include <math.h>
#include <complex.h>	// Use native C99 complex type for fftw3
#include "quisk.h"

static enum {
	Unknown,
	None,
	Four,
	Five,
	Eight,
	FiveFour,
	FiveEight,
	FourEight,
	ThreeEight,
	TwoEight
} idecim_scheme;

// Decimation filters are Parks-McClellan FIR Filter Design:
// Order: 81
// Passband ripple: 0.1 dB
// Transition band: 0.05
// Stopband attenuation: 100.0 dB

#define DEC_FILT_TAPS		82

static double dec_filt_four[DEC_FILT_TAPS] = {	// 0.200 bandwidth for 1/4
6.93262847909316E-5, 1.6197926963904747E-4, -2.978880216503281E-5, -7.607072256017523E-4,
-0.0015328465141652313, -0.0012468590175053562, 2.610559866853963E-4, 0.0012944734487453414,
2.3302486450800912E-4, -0.0016407424838786528, -0.0012416553276332963, 0.0015073572516228356,
0.00246088370832881, -7.03592657698059E-4, -0.003615088283354994, -9.287652193144898E-4,
0.004243002194452015, 0.003314623044307713, -0.003839298846344248, -0.006115837049852382,
0.0019601369874323576, 0.008710630191084028, 0.0016299333322581358, -0.010249913305703927,
-0.006832131686428464, 0.009766175058001373, 0.013128572492857463, -0.006308334625132938,
-0.019542504322817577, -9.249612897081307E-4, 0.024651789635613427, 0.012545482681757834,
-0.026576155055309945, -0.029184569947365617, 0.022677733544428112, 0.0524099453299258,
-0.007945906430265487, -0.08887991706016465, -0.03541624039036922, 0.18706014148382252,
0.4027578624778919, 0.4027578624778919, 0.18706014148382252, -0.03541624039036922,
-0.08887991706016465, -0.007945906430265487, 0.0524099453299258, 0.022677733544428112,
-0.029184569947365617, -0.026576155055309945, 0.012545482681757834, 0.024651789635613427,
-9.249612897081307E-4, -0.019542504322817577, -0.006308334625132938, 0.013128572492857463,
0.009766175058001373, -0.006832131686428464, -0.010249913305703927, 0.0016299333322581358,
0.008710630191084028, 0.0019601369874323576, -0.006115837049852382, -0.003839298846344248,
0.003314623044307713, 0.004243002194452015, -9.287652193144898E-4, -0.003615088283354994,
-7.03592657698059E-4, 0.00246088370832881, 0.0015073572516228356, -0.0012416553276332963,
-0.0016407424838786528, 2.3302486450800912E-4, 0.0012944734487453414, 2.610559866853963E-4,
-0.0012468590175053562, -0.0015328465141652313, -7.607072256017523E-4, -2.978880216503281E-5,
1.6197926963904747E-4, 6.93262847909316E-5};

static double dec_filt_five[DEC_FILT_TAPS] = {	// 0.150 bandwidth for 1/5
4.802945694175824E-5, 1.3678129104226564E-4, 1.5780237068504314E-4, -9.447967308879232E-5,
-7.096795320832177E-4, -0.001401250667455834, -0.0015400533718900225, -6.747045776483936E-4,
8.153280522959677E-4, 0.0016993691656680282, 8.936602390940594E-4, -0.0012352048814478292,
-0.002710208527872082, -0.001616712517641334, 0.0016582434482831638, 0.004079060014727778,
0.0026053079020420494, -0.0022732852688599737, -0.0059919633490814915, -0.003956217667702122,
0.003149204678409682, 0.008619113656227065, 0.00575247818483739, -0.004432293133200357,
-0.012256528072905008, -0.008148410734226686, 0.006362564035902175, 0.01743705847413967,
0.011452631286430849, -0.00939474436497328, -0.025278755048946437, -0.016382944751566725,
0.014588955459961006, 0.03869591981083795, 0.02505025857670139, -0.025262163858126217,
-0.0684261501517449, -0.04695060459326292, 0.060595955694417517, 0.21142646204362847,
0.32063462646029334, 0.32063462646029334, 0.21142646204362847, 0.060595955694417517,
-0.04695060459326292, -0.0684261501517449, -0.025262163858126217, 0.02505025857670139,
0.03869591981083795, 0.014588955459961006, -0.016382944751566725, -0.025278755048946437,
-0.00939474436497328, 0.011452631286430849, 0.01743705847413967, 0.006362564035902175,
-0.008148410734226686, -0.012256528072905008, -0.004432293133200357, 0.00575247818483739,
0.008619113656227065, 0.003149204678409682, -0.003956217667702122, -0.0059919633490814915,
-0.0022732852688599737, 0.0026053079020420494, 0.004079060014727778, 0.0016582434482831638,
-0.001616712517641334, -0.002710208527872082, -0.0012352048814478292, 8.936602390940594E-4,
0.0016993691656680282, 8.153280522959677E-4, -6.747045776483936E-4, -0.0015400533718900225,
-0.001401250667455834, -7.096795320832177E-4, -9.447967308879232E-5, 1.5780237068504314E-4,
1.3678129104226564E-4, 4.802945694175824E-5};

static double dec_filt_eight[DEC_FILT_TAPS] = {	// 0.075 bandwidth for 1/8
3.189499939137948E-5, 9.658000074768447E-5, 2.066544953451926E-4, 3.44452671428755E-4,
4.5985201258950855E-4, 4.7151300219738324E-4, 2.884095680130089E-4, -1.4972784756879228E-4,
-8.240738514407132E-4, -0.001601285443271075, -0.0022351411796416518, -0.0024218067343669786,
-0.0019063148533499982, -6.12297195964114E-4, 0.0012546716666281578, 0.0031864584051393505,
0.004473200480571965, 0.004424166162645936, 0.0026536808739181, -6.675516541696363E-4,
-0.004711222046697417, -0.00812616121435781, -0.00942114518562818, -0.007510029585918773,
-0.0022454680141598088, 0.00527145304120975, 0.012781816045613894, 0.017422645491741433,
0.016645094307362603, 0.009241600363100413, -0.0038641474640177136, -0.019390756369107805,
-0.032221251420502695, -0.036629981372148956, -0.02792435737553998, -0.004033420538463705,
0.03346490593697525, 0.07926024983841577, 0.12528860198355965, 0.16256947281001224,
0.18341920540549964, 0.18341920540549964, 0.16256947281001224, 0.12528860198355965,
0.07926024983841577, 0.03346490593697525, -0.004033420538463705, -0.02792435737553998,
-0.036629981372148956, -0.032221251420502695, -0.019390756369107805, -0.0038641474640177136,
0.009241600363100413, 0.016645094307362603, 0.017422645491741433, 0.012781816045613894,
0.00527145304120975, -0.0022454680141598088, -0.007510029585918773, -0.00942114518562818,
-0.00812616121435781, -0.004711222046697417, -6.675516541696363E-4, 0.0026536808739181,
0.004424166162645936, 0.004473200480571965, 0.0031864584051393505, 0.0012546716666281578,
-6.12297195964114E-4, -0.0019063148533499982, -0.0024218067343669786, -0.0022351411796416518,
-0.001601285443271075, -8.240738514407132E-4, -1.4972784756879228E-4, 2.884095680130089E-4,
4.7151300219738324E-4, 4.5985201258950855E-4, 3.44452671428755E-4, 2.066544953451926E-4,
9.658000074768447E-5, 3.189499939137948E-5};

static int iDecimateFour(complex * cSamples, int nSamples, int idecim)
{  // Decimate to a lower sample rate by an integer idecim 2 through 4
	int i, j, k, n;
	complex cx;
	static int findex = 0;
	static complex bufDecim[MAX_FILTER_SIZE];
	static int counter = 0;

	n = 0;
	for (i = 0; i < nSamples; i++) {
		bufDecim[findex] = cSamples[i];
		if (++counter >= idecim) {
			counter = 0;		// output a sample
			cx = 0;
			j = findex;
			for (k = 0; k < DEC_FILT_TAPS; k++) {
				cx += bufDecim[j] * dec_filt_four[k];
				if (++j >= DEC_FILT_TAPS)
					j = 0;
			}
			cSamples[n++] = cx;
		}
		if (++findex >= DEC_FILT_TAPS)
			findex = 0;
	}
	return n;
}

static int iDecimateFive(complex * cSamples, int nSamples, int idecim)
{  // Decimate to a lower sample rate by an integer idecim 2 through 5
	int i, j, k, n;
	complex cx;
	static int findex = 0;
	static complex bufDecim[MAX_FILTER_SIZE];
	static int counter = 0;

	n = 0;
	for (i = 0; i < nSamples; i++) {
		bufDecim[findex] = cSamples[i];
		if (++counter >= idecim) {
			counter = 0;		// output a sample
			cx = 0;
			j = findex;
			for (k = 0; k < DEC_FILT_TAPS; k++) {
				cx += bufDecim[j] * dec_filt_five[k];
				if (++j >= DEC_FILT_TAPS)
					j = 0;
			}
			cSamples[n++] = cx;
		}
		if (++findex >= DEC_FILT_TAPS)
			findex = 0;
	}
	return n;
}

static int iDecimateEight(complex * cSamples, int nSamples, int idecim)
{  // Decimate to a lower sample rate by an integer idecim 2 through 8
	int i, j, k, n;
	complex cx;
	static int findex = 0;
	static complex bufDecim[MAX_FILTER_SIZE];
	static int counter = 0;

	n = 0;
	for (i = 0; i < nSamples; i++) {
		bufDecim[findex] = cSamples[i];
		if (++counter >= idecim) {
			counter = 0;		// output a sample
			cx = 0;
			j = findex;
			for (k = 0; k < DEC_FILT_TAPS; k++) {
				cx += bufDecim[j] * dec_filt_eight[k];
				if (++j >= DEC_FILT_TAPS)
					j = 0;
			}
			cSamples[n++] = cx;
		}
		if (++findex >= DEC_FILT_TAPS)
			findex = 0;
	}
	return n;
}

// Decimate: Lower the sample rate by idecim.  This function uses
// static storage, and there must be only one call to it in the program.
// Using two calls to decimate two sample streams will not work.
// Check the resulting bandwidth for your decimation, as it will
// generally be much less than the maximum.
int quisk_iDecimate(complex * cSamples, int nSamples, int idecim)
{
	static int old_idecim = 0;		// previous value of idecim

	if (idecim != old_idecim) {		// Initialization
		old_idecim = idecim;
		if (idecim <= 1)	// Set the correct decimation filter based on rate reduction.
			idecim_scheme = None;
		else if (idecim <= 4)
			idecim_scheme = Four;
		else if (idecim == 5)
			idecim_scheme = Five;
		else if (idecim <= 8)
			idecim_scheme = Eight;
		else if (idecim % 5 == 0) {		// good for 10, 15, ..., 40
			if (idecim / 5 <= 4)
				idecim_scheme = FiveFour;
			else
				idecim_scheme = FiveEight;
		}
		else if (idecim % 4 == 0)
			idecim_scheme = FourEight;
		else if (idecim % 3 == 0)
			idecim_scheme = ThreeEight;
		else if (idecim % 2 == 0)
			idecim_scheme = TwoEight;
		else		// There is no good scheme, and this filter is inadequate
			idecim_scheme = Eight;
	}
	switch (idecim_scheme) {
		case None:
			break;
		case Four:
			nSamples = iDecimateFour(cSamples, nSamples, idecim);
			break;
		case Five:
			nSamples = iDecimateFive(cSamples, nSamples, idecim);
			break;
		case Eight:
			nSamples = iDecimateEight(cSamples, nSamples, idecim);
			break;
		case FiveFour:
			nSamples = iDecimateFive(cSamples, nSamples, 5);
			nSamples = iDecimateFour(cSamples, nSamples, idecim / 5);
			break;
		case FiveEight:
			nSamples = iDecimateFive(cSamples, nSamples, 5);
			nSamples = iDecimateEight(cSamples, nSamples, idecim / 5);
			break;
		case FourEight:
			nSamples = iDecimateFour(cSamples, nSamples, 4);
			nSamples = iDecimateEight(cSamples, nSamples, idecim / 4);
			break;
		case ThreeEight:
			nSamples = iDecimateFour(cSamples, nSamples, 3);
			nSamples = iDecimateEight(cSamples, nSamples, idecim / 3);
			break;
		case TwoEight:
			nSamples = iDecimateFour(cSamples, nSamples, 2);
			nSamples = iDecimateEight(cSamples, nSamples, idecim / 2);
			break;
		default:		// should not happen
			nSamples = iDecimateEight(cSamples, nSamples, idecim);
			break;
	}
	return nSamples;	// return the new number of samples
}
