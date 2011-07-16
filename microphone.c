#include <Python.h>
#include <stdlib.h>
#include <math.h>
#include <sys/timeb.h>
#include <complex.h>
#include <fftw3.h>
#include "quisk.h"
#include <sys/types.h>
#include "microphone.h"

#ifdef MS_WINDOWS
#include <Winsock2.h>
static int mic_cleanup = 0;		// must clean up winsock
#else
#include <sys/socket.h>
#include <arpa/inet.h>
#define		INVALID_SOCKET	-1
#endif

#define DEBUG	0

// FM needs pre-emphasis and de-emphasis.  See vk1od.net/FM/FM.htm for details.
// For IIR design, see http://www.abvolt.com/research/publications2.htm.

// TX_FILTER_1: cutoff frequency in Hertz for first transmit high pass filter
#define TX_FILTER_1		3000.0
// Microhone preemphasis: boost high frequencies 0.00 to 1.00; or -1.0 for Butterworth
double quisk_mic_preemphasis;
// Microphone clipping; try 3.0 or 4.0
double quisk_mic_clip;

#define MIC_AVG_GAIN	10.0	// Typical gain for the microphone in use
#define MIC_MAX_GAIN	100.0	// Do not increase gain over this value

// These are external:
int mic_max_display;			// display value of maximum microphone signal level 0 to 2**15 - 1

static int mic_socket = INVALID_SOCKET;	// send microphone samples to a socket
static int spotMode = 0;		// 0 for no spotting; else 1 for small signal, 2 for full signal

static int mic_level;			// maximum microphone signal level for display
static int mic_timer;			// time to display maximum mic level
static int align4;				// add two bytes to start of audio samples to align to 4 bytes

static double * txFilterI;		// Digital filters for transmit audio
static double * txFilterQ;
static double * txFilterC;
static double * txFilterBufI;
static double * txFilterBufQ;
static complex * txFilterBufC;
static int txFilterIQSize, txFilterCSize;

#define TX_BLOCK_SHORTS		600		// transmit UDP packet with this many shorts (two bytes) (perhaps + 1)
#define MIC_MAX_HOLD_TIME	400		// Time to hold the maximum mic level on the Status screen in milliseconds

// These IIR coefficients are for a Butterworth 16 order filter.
// The assumed sample rate is 48000 Hz.  Calculation by dsptutor; 8000 rate, 1775-2225 BW.
// At 48 kHz: 10650 - 13350; 300 - 3000 -> USB 10350, LSB -> 13650.
#define IIR_ORDER	16
static double AA[IIR_ORDER + 1] = {
 4.1547196E-7, 0.0, -3.3237757E-6, 0.0,
1.1633215E-5, 0.0, -2.326643E-5, 0.0, 2.9083038E-5,
0.0, -2.326643E-5, 0.0, 1.1633215E-5, 0.0,
-3.3237757E-6, 0.0, 4.1547196E-7
};
static double BB[IIR_ORDER + 1] = {
 1.0, -8.7430063E-16, 6.189361, -4.6074256E-15,
16.925411, -1.060263E-14, 26.68181, -1.4044321E-14, 26.499163,
-1.110223E-14, 16.966507, -5.2735594E-15, 6.8351107, -1.3877788E-15,
1.5832834, -1.6132928E-16, 0.16138433
};

// If TEST_TX_WAV_FILE is defined, then this file is used as the transmit
// audio source.  Otherwise the microphone (if any) is used.  The
// WAV file must be recorded at 48000 Hertz in S16_LE format.
// For example: #define TEST_TX_WAV_FILE "/home/jim/quisk/quisk_test.wav"

//#define TEST_TX_WAV_FILE	"/home/jim/quisk/notdist/quisk.wav"
#define USE_GET_SIN		0

#ifdef TEST_TX_WAV_FILE
static int wavStart;			// Sound data starts at this offset
static int wavEnd;				// End of sound data
static FILE * wavFp;			// File pointer for WAV file input

static void open_wav(void)
{
	char name[5];
	long size;

	if (!wavFp) {		// Open sound test file
		wavFp = fopen(TEST_TX_WAV_FILE, "rb");
		if (!wavFp) {
			printf("open_wav failed\n");
			return;
		}
		wavEnd = 0;
		while (1) {
			if (fread (name, 4, 1, wavFp) != 1)
				break;
			fread (&size, 4, 1, wavFp);
			name[4] = 0;
			//printf("name %s size %ld\n", name, size);
			if (!strncmp(name, "RIFF", 4))
				fseek (wavFp, 4, SEEK_CUR);	// Skip "WAVE"
			else if (!strncmp(name, "data", 4)) {	// sound data starts here
				wavStart = ftell(wavFp);
				wavEnd = wavStart + size;
				break;
			}
			else	// Skip other records
				fseek (wavFp, size, SEEK_CUR);
		}
		//printf("start %d  end %d\n", wavStart, wavEnd);
		if (!wavEnd) {		// Failure to find "data" record
			fclose(wavFp);
			wavFp = NULL;
		}
	}
}

static void get_wav(complex * buffer, int count)
{
	// Put transmit audio samples from a file into buffer
	int pos, i;
	short sh;

	if (wavFp) {
		pos = ftell (wavFp);
		for (i = 0; i < count; i++) {
			fread(&sh, 2, 1, wavFp);
			buffer[i] = sh * ((double)CLIP32 / CLIP16);
			if (++pos >= wavEnd) {
				fseek (wavFp, wavStart, SEEK_SET);
				pos = wavStart;
			}
		}
	}
}
#endif

#if USE_GET_SIN
static void get_sin(complex * buffer, int count)
{	// replace mic samples with a sin wave
	static complex phase = 0;
	static complex vector = CLIP32;
	int i;

	if (phase == 0)
		phase = cexp((I * 2.0 * M_PI * 1000.0) / quisk_sound_state.mic_sample_rate);
	for (i = 0; i < count; i++) {
		vector *= phase;
		buffer[i] = vector;
	}
}
#endif

static void tx_filter(complex * filtered, int count)
{	// Input samples are creal(filtered), output is filtered.
	int i, j, k;
	double x, y, www, nnn, accI, accQ, dtmp, peakA, peakB;
	complex csample, cy;

	static double * fltI, * fltQ;
	static int bufIQindex, bufCindex;
	static double gainA = MIC_AVG_GAIN, gainB = 1;
	static double a_0, a_1, b_1, x_1, y_1;
	static complex cX[16], cY[16];
	static complex tuneUpPhase, tuneUpVector, tuneDownPhase, tuneDownVector;

	if (!filtered) {		// initialization
		www = tan(M_PI * TX_FILTER_1 / quisk_sound_state.mic_sample_rate);
		nnn = 1.0 / (1.0 + www);
		a_0 = nnn;
		a_1 = - nnn;
		b_1 = nnn * (www - 1.0);
		x_1 = y_1 = 0;
		bufIQindex = 0;
		bufCindex = 0;
		tuneUpVector = tuneDownVector = 1;
		for (i = 0; i < txFilterIQSize; i++)
			txFilterBufI[i] = txFilterBufQ[i] = 0;
		for (i = 0; i < 17; i++)
			cX[i] = cY[i] = 0;
		if (rxMode == 2) {			// LSB
			fltI = txFilterQ;
			fltQ = txFilterI;
			tuneUpPhase   = cexp(I * 2.0 * M_PI  * 13650.0/ quisk_sound_state.mic_sample_rate);
			tuneDownPhase = cexp(I * 2.0 * M_PI  * 12000.0/ quisk_sound_state.mic_sample_rate);
		}
		else if (rxMode == 3) {		// USB
			fltI = txFilterI;
			fltQ = txFilterQ;
			tuneUpPhase   = cexp(I * 2.0 * M_PI  * 10350.0/ quisk_sound_state.mic_sample_rate);
			tuneDownPhase = cexp(I * 2.0 * M_PI  * 12000.0/ quisk_sound_state.mic_sample_rate);
		}
		else {
			fltI = fltQ = NULL;
			tuneUpPhase = 0;
		}
		// For UDP and USB/LSB, the center of the passband is at zero hertz, and a
		// correction of 1650 Hertz is made in the transmit frequency tuning.
		if (quisk_sound_state.tx_audio_port == 0)	// Test for UDP
			tuneDownPhase = tuneUpPhase;	// For no UDP, leave audio at same frequency.
		return;
	}
#if USE_GET_SIN
	return;
#endif
#if DEBUG
	{
	static long timer = 0;		// count up number of samples
		timer += count;
		if (timer >= quisk_sound_state.mic_sample_rate) {		// one second
			timer = 0;
			printf("gainA %8.2f  gainB %8.2f  count%d\n", gainA, gainB, count);
		}
	}
#endif
	peakA = 1;
	peakB = 1;
	for (i = 0; i < count; i++) {
		csample = creal(filtered[i]);
		if ( ! fltI) {	// just so filters are zero except for LSB/USB
			filtered[i] = 0;
			continue;
		}
		if (quisk_mic_preemphasis < 0.0) {
			// high pass filter for preemphasis; Butterworth 1st order
			x = creal(filtered[i]);
			y = a_0 * x + a_1 * x_1 - b_1 * y_1;
			x_1 = x;
			y_1 = y;
			csample = y + I * y;
		}
		else {
			// high pass filter for preemphasis: See Radcom, January 2010, page 76.
			x = creal(csample);
			csample = x - quisk_mic_preemphasis * x_1;
			x_1 = x;	// delayed sample
		}
#if 1
		// FIR bandpass filter; separate into I and Q
		txFilterBufI[bufIQindex] = creal(csample);
		txFilterBufQ[bufIQindex] = creal(csample);
		accI = accQ = 0;
		j = bufIQindex;
		for (k = 0; k < txFilterIQSize; k++) {
			accI += txFilterBufI[j] * fltI[k];
			accQ += txFilterBufQ[j] * fltQ[k];
			if (++j >= txFilterIQSize)
				j = 0;
		}
		if (++bufIQindex >= txFilterIQSize)
			bufIQindex = 0;
		csample = accI + I * accQ;
#endif
#if 1
		// Tune the data up to higher frequency
		csample *= tuneUpVector;
		tuneUpVector *= tuneUpPhase;
#endif

#if 1
		// normalize amplitude
		dtmp = cabs(csample);
		if (dtmp > peakA)
			peakA = dtmp;
		// Increase gain slowly
		gainA *= 1.0 + 0.1 / quisk_sound_state.mic_sample_rate;
		// Limit to maximum gain
		dtmp = CLIP16 * quisk_mic_clip / peakA;
		if (gainA > dtmp)
			gainA = dtmp;
		if (gainA > MIC_MAX_GAIN)
			gainA = MIC_MAX_GAIN;
		csample *= gainA;
#endif
#if 1
		// clip signal
		dtmp = cabs(csample);
        if (dtmp > CLIP16)
			csample *= CLIP16 / dtmp;
#endif
#if 0
		// FIR filter to rempve clipping distortion
		if (txFilterCSize > 0) {
			txFilterBufC[bufCindex] = csample;
			cy = 0;
			j = bufCindex;
			for (k = 0; k < txFilterCSize; k++) {
				cy += txFilterBufC[j] * txFilterC[k];
				if (++j >= txFilterCSize)
					j = 0;
			}
			if (++bufCindex >= txFilterCSize)
				bufCindex = 0;
			csample = cy;
		}
#endif
#if 1
		// IIR filter to remove clipping distortion
		cy = 0;
		for (j = 2; j <= IIR_ORDER; j += 2)
			cy += AA[j] * cX[j] - BB[j] * cY[j];
		for (j = IIR_ORDER; j > 0; j--) {
			cX[j] = cX[j - 1];
			cY[j] = cY[j - 1];
		}
		cX[1] = csample;
		cY[1] = cy;
		csample = cy;
#endif
#if 1
		// Tune the data back down to frequency
		csample *= tuneDownVector;
		tuneDownVector /= tuneDownPhase;
#endif
#if 1
		// Normalize final amplitude
		dtmp = cabs(csample);
		if (dtmp > peakB)
			peakB = dtmp;
		// Increase gain at 6db per second
		gainB *= 1.0 + 0.693 / quisk_sound_state.mic_sample_rate;
		// Limit to maximum gain
		dtmp = CLIP16 / peakB;
		if (gainB > dtmp)
			gainB = dtmp;
		if (gainB > 2.0)	// gainB should be about 1.0
			gainB = 2.0;
		csample *= gainB;
#endif
		filtered[i] = csample;
	}
}

static void tx_filter2(complex * filtered, int count)
{	// Input samples are creal(filtered), output is creal(filtered).
	// The mic sample rate must be 48000 sps.
	int i, j, k;
	double dsample, x, y, www, nnn, accI, accQ, dtmp, peakA, peakB;

	static int bufHindex, buf2index;
	static double gainA = MIC_AVG_GAIN, gainB = 1;
	static double a_0, a_1, b_1, x_1, y_1;
	static double txFilterBufH[txFilterHSize];
	static double txFilterBuf2[txFilter2Size];
#if DEBUG
	static long timer = 0;		// count up number of samples
	double peakC;
#endif

	if (!filtered) {		// initialization
		www = tan(M_PI * TX_FILTER_1 / quisk_sound_state.mic_sample_rate);
		nnn = 1.0 / (1.0 + www);
		a_0 = nnn;
		a_1 = - nnn;
		b_1 = nnn * (www - 1.0);
		x_1 = y_1 = 0;
		buf2index = bufHindex = 0;
		for (i = 0; i < txFilter2Size; i++)
			txFilterBuf2[i] = 0;
		for (i = 0; i < txFilterHSize; i++)
			txFilterBufH[i] = 0;
		return;
	}
#if USE_GET_SIN
	return;
#endif
#if DEBUG
	timer += count;
	if (timer >= quisk_sound_state.mic_sample_rate) {		// one second
		timer = 0;
		printf("gainA %8.2f  gainB %8.2f  count%d\n", gainA, gainB, count);
	}
	peakC = 0;
#endif
	peakA = peakB = 1;
	for (i = 0; i < count; i++) {
		dsample = creal(filtered[i]);
#if 1
		if (quisk_mic_preemphasis < 0.0) {
			// high pass filter for preemphasis; Butterworth 1st order
			x = dsample;
			y = a_0 * x + a_1 * x_1 - b_1 * y_1;
			x_1 = x;
			y_1 = y;
			dsample = y;
		}
		else {
			// high pass filter for preemphasis: See Radcom, January 2010, page 76.
			x = dsample;
			dsample = x - quisk_mic_preemphasis * x_1;
			x_1 = x;	// delayed sample
		}
#endif
		// Normalize amplitude
		dtmp = fabs(dsample);
		if (dtmp > peakA)
			peakA = dtmp;
#if 1
		gainA *= 1.0 + 0.1 / quisk_sound_state.mic_sample_rate;	// Increase gain slowly
		dtmp = CLIP16 / peakA;
		if (gainA > dtmp)			// Limit gain
			gainA = dtmp;
		if (gainA > MIC_MAX_GAIN)	// Limit to maximum gain
			gainA = MIC_MAX_GAIN;
		dsample *= gainA;
#endif
#if 1
		// Hilbert filter to clip audio
		dsample *= quisk_mic_clip;
		txFilterBufH[bufHindex] = dsample;	// newest sample
		j = bufHindex + 1;	// start at oldest sample
		if (j >= txFilterHSize)
			j -= txFilterHSize;
		accQ = 0;
		for (k = 0; k < txFilterHSize; k+=2) {
			accQ += txFilterBufH[j] * txFilterH[k];
			j += 2;
			if (j >= txFilterHSize)
				j -= txFilterHSize;
		}
		accQ /= HILBERT_GAIN;
		j = bufHindex + 1 + txFilterHSize / 2;	// midpoint of filter
		if (j >= txFilterHSize)
			j -= txFilterHSize;
		accI = txFilterBufH[j];
		if (++bufHindex >= txFilterHSize)
			bufHindex = 0;
		dtmp = sqrt(accI * accI + accQ * accQ);
		if (dtmp > CLIP16)	// perform clipping
			dsample = accI * CLIP16 / dtmp;
		else
			dsample = accI;
#endif
#if 1
		// FIR bandpass filter
		txFilterBuf2[buf2index] = dsample;
		accI = 0;
		j = buf2index;
		for (k = 0; k < txFilter2Size; k++) {
			accI += txFilterBuf2[j] * txFilter2[k];
			if (++j >= txFilter2Size)
				j = 0;
		}
		if (++buf2index >= txFilter2Size)
			buf2index = 0;
		dsample = accI * 8.0;
#endif
#if 1
		// Normalize final amplitude
		dtmp = fabs(dsample);
		if (dtmp > peakB)
			peakB = dtmp;
		// Increase gain at 6db per second
		gainB *= 1.0 + 0.693 / quisk_sound_state.mic_sample_rate;
		// Limit to maximum gain
		dtmp = CLIP16 / peakB;
		if (gainB > dtmp)
			gainB = dtmp;
		if (gainB > 2.0)	// gainB should be about 1.0
			gainB = 2.0;
		dsample *= gainB;
#endif
		filtered[i] = dsample;
#if DEBUG
		dtmp = fabs(dsample);
		if (dtmp > peakC)
			peakC = dtmp;
#endif
	}
#if DEBUG
	if (timer == 0)
		printf ("peakA %.0f  peakB %.0f  peakC %.0f\n", peakA, peakB, peakC);
#endif
}

PyObject * quisk_get_tx_filter(PyObject * self, PyObject * args)
{  // return the TX filter response to display on the graph
// This is for debugging.  Change quisk.py to call QS.get_tx_filter() instead
// of QS.get_filter(), and make sure set_tx_filters() is called.
	int i, j, k;
	int freq, time;
	PyObject * tuple2;
	complex cx;
	double scale;
	double * average, * fft_window, * bufI, * bufQ;
	fftw_complex * samples, * pt;		// complex data for fft
	fftw_plan plan;						// fft plan
	double phase, delta;

	if (!PyArg_ParseTuple (args, ""))
		return NULL;

	// Create space for the fft of size data_width
	pt = samples = (fftw_complex *) fftw_malloc(sizeof(fftw_complex) * data_width);
	plan = fftw_plan_dft_1d(data_width, pt, pt, FFTW_FORWARD, FFTW_MEASURE);
	average = (double *) malloc(sizeof(double) * (data_width + txFilterIQSize));
	fft_window = (double *) malloc(sizeof(double) * data_width);
	bufI = (double *) malloc(sizeof(double) * txFilterIQSize);
	bufQ = (double *) malloc(sizeof(double) * txFilterIQSize);

	for (i = 0, j = -data_width / 2; i < data_width; i++, j++)	// Hanning
		fft_window[i] = 0.5 + 0.5 * cos(2. * M_PI * j / data_width);

	for (i = 0; i < data_width + txFilterIQSize; i++)
		average[i] = 0.5;	// Value for freq == 0
	for (freq = 1; freq < data_width / 2.0 - 10.0; freq++) {
	//freq = data_width * 0.2 / 48.0;
		delta = 2 * M_PI / data_width * freq;
		phase = 0;
		// generate some initial samples to fill the filter pipeline
		for (time = 0; time < data_width + txFilterIQSize; time++) {
			average[time] += cos(phase);	// current sample
			phase += delta;
			if (phase > 2 * M_PI)
				phase -= 2 * M_PI;
		}
	}
	// now filter the signal using the transmit filter
	tx_filter2(NULL, 0);								// initialize
    scale = 1.0;
	for (i = 0; i < data_width; i++)
		if (fabs(average[i + txFilterIQSize]) > scale)
			scale = fabs(average[i + txFilterIQSize]);
	scale = CLIP16 / scale;		// limit to CLIP16
	for (i = 0; i < txFilterIQSize; i++)
		samples[i] = average[i] * scale;
	tx_filter2(samples, txFilterIQSize);			// process initial samples
	for (i = 0; i < data_width; i++)
		samples[i] = average[i + txFilterIQSize] * scale;
	tx_filter2(samples, data_width);	// process the samples

	for (i = 0; i < data_width; i++)	// multiply by window
		samples[i] *= fft_window[i];
	fftw_execute(plan);		// Calculate FFT
	// Normalize and convert to log10
	scale = 0.3 / data_width / scale;
	for (k = 0; k < data_width; k++) {
		cx = samples[k];
		average[k] = cabs(cx) * scale;
		if (average[k] <= 1e-7)		// limit to -140 dB
			average[k] = -7;
		else
			average[k] = log10(average[k]);
	}
	// Return the graph data
	tuple2 = PyTuple_New(data_width);
	i = 0;
	// Negative frequencies:
	for (k = data_width / 2; k < data_width; k++, i++)
		PyTuple_SetItem(tuple2, i, PyFloat_FromDouble(20.0 * average[k]));

	// Positive frequencies:
	for (k = 0; k < data_width / 2; k++, i++)
		PyTuple_SetItem(tuple2, i, PyFloat_FromDouble(20.0 * average[k]));

	free(bufQ);
	free(bufI);
	free(average);
	free(fft_window);
	fftw_destroy_plan(plan);
	fftw_free(samples);

	return tuple2;
}

// udp_iq has an initial zero followed by the I/Q samples.
// The initial zero is sent iff align4 == 1.

static void transmit_udp(complex * cSamples, int count)
{	// Send count samples.  Each sample is sent as two shorts (4 bytes) of I/Q data.
	// Transmission is delayed until a whole block of data is available.
	int i, sent;
	static short udp_iq[TX_BLOCK_SHORTS + 1] = {0};
	static int udp_size = 1;
	double vol;

	if (mic_socket == INVALID_SOCKET)
		return;
	if ( ! cSamples) {		// initialization
		udp_size = 1;
		udp_iq[0] = 0;	// should not be necessary
		return;
	}
	vol = quisk_sound_state.mic_out_volume;
	for (i = 0; i < count; i++) {	// transmit samples
		udp_iq[udp_size++] = (short)(creal(cSamples[i]) * vol);
		udp_iq[udp_size++] = (short)(cimag(cSamples[i]) * vol);
		if (udp_size >= TX_BLOCK_SHORTS) {	// check count
			if (align4)
				sent = send(mic_socket, (char *)udp_iq, udp_size * 2, 0);
			else
				sent = send(mic_socket, (char *)udp_iq + 1, --udp_size * 2, 0);
			if (sent != udp_size * 2)
				printf("Send socket returned %d\n", sent);
			udp_size = 1;
		}
	}
}

static void transmit_mic_carrier(complex * cSamples, int count, double level)
{	// send a CW carrier instead of mic samples
	int i;

	for (i = 0; i < count; i++)		// transmit a carrier equal to the number of samples
		cSamples[i] = level * CLIP16;
	transmit_udp(cSamples, count);
}

static void transmit_mic_imd(complex * cSamples, int count, double level)
{	// send a 2-tone test signal instead of mic samples
	int i;
	complex v;
	static complex phase1=0, phase2;		// Phase increment
	static complex vector1;
	static complex vector2;

	if (phase1 == 0) {		// initialize
		phase1 = cexp((I * 2.0 * M_PI * IMD_TONE_1) / quisk_sound_state.mic_sample_rate);
		phase2 = cexp((I * 2.0 * M_PI * IMD_TONE_2) / quisk_sound_state.mic_sample_rate);
		vector1 = CLIP16 / 2.0;
		vector2 = CLIP16 / 2.0;
	}
	for (i = 0; i < count; i++) {	// transmit a carrier equal to the number of samples
		vector1 *= phase1;
		vector2 *= phase2;
		v = level * (vector1 + vector2);
		cSamples[i] = v;
	}
	transmit_udp(cSamples, count);
}

int quisk_process_microphone(complex * cSamples, int count)
{
	int i, sample, maximum;
	double d;
	static double fmPhase = CLIP16;

#if 0
	// Measure soundcard actual sample rate
	static time_t seconds = 0;
	static long total = 0;
	struct timeb tb;
	static double dtime;

	ftime(&tb);
	total += count;
	if (seconds == 0) {
		seconds = tb.time;
		dtime = tb.time + .001 * tb.millitm;
	}		
	else if (tb.time - seconds > 4) {
		printf("Mic soundcard rate %.3f\n", total / (tb.time + .001 * tb.millitm - dtime));
		seconds = tb.time;
		printf("backlog %d, count %d\n", backlog, count);
	}
#endif

	
#ifdef TEST_TX_WAV_FILE
	get_wav(cSamples, count);	// replace audio samples with sound from a WAV file
#endif
#if USE_GET_SIN
	get_sin(cSamples, count);	// Replace mic samples with a sin wave, and send it
#endif
	maximum = 1;
	for (i = 0; i < count; i++) {	// measure maximum microphone level for display
		cSamples[i] *= (double)CLIP16 / CLIP32;	// convert 32-bit samples to 16 bits
		d = creal(cSamples[i]);
		sample = (int)fabs(d);
		if (sample > maximum)
			maximum = sample;
	}
	if (maximum > mic_level)
		mic_level = maximum;
	mic_timer -= count;		// time out the max microphone level to display
	if (mic_timer <= 0) {
		mic_timer = quisk_sound_state.mic_sample_rate / 1000 * MIC_MAX_HOLD_TIME;
		mic_max_display = mic_level;
		mic_level = 1;
	}

	if (quisk_is_key_down())
		switch (rxMode) {
		case 2:		// LSB
		case 3:		// USB
			if (spotMode == 0) {
				tx_filter(cSamples, count);	// filter samples
				transmit_udp(cSamples, count);
			}
			else if (spotMode == 1)
				transmit_mic_carrier(cSamples, count, 0.5);
			else
				transmit_mic_carrier(cSamples, count, 1.0);
			break;
		case 4:		// AM
			tx_filter2(cSamples, count);
			for (i = 0; i < count; i++)	// transmit (0.5 + ampl/2, 0)
				cSamples[i] = (creal(cSamples[i]) + CLIP16) * 0.5;
			transmit_udp(cSamples, count);
			break;
		case 5999:		// FM
			tx_filter2(cSamples, count);
			for (i = 0; i < count; i++) {	// transmit +/- 5000 Hz tone
				fmPhase *= cexp( - I * 2.0 * M_PI * (5000.0 * creal(cSamples[i]) / CLIP16) /
					quisk_sound_state.mic_sample_rate);
				cSamples[i] = fmPhase;
			}
			transmit_udp(cSamples, count);
			break;
		case 10:	// transmit IMD 2-tone test
			transmit_mic_imd(cSamples, count, 1.0);
			break;
		case 11:
			transmit_mic_imd(cSamples, count, 1.0 / sqrt(2.0));
			break;
		case 12:
			transmit_mic_imd(cSamples, count, 0.5);
			break;
		}
	else
		fmPhase = CLIP16;
	return count;
}

void quisk_close_mic(void)
{
	if (mic_socket != INVALID_SOCKET) {
		close(mic_socket);
		mic_socket = INVALID_SOCKET;
	}
#ifdef MS_WINDOWS
	if (mic_cleanup)
		WSACleanup();
#endif
}

void quisk_open_mic(void)
{
	struct sockaddr_in Addr;

	if (quisk_sound_state.tx_audio_port == 0x553B)
		align4 = 0;		// Using old port: data starts at byte 42.
	else
		align4 = 1;		// Start data at byte 44; align to dword
	if (quisk_sound_state.mic_ip[0]) {
#ifdef MS_WINDOWS
		{
			WORD wVersionRequested;
			WSADATA wsaData;
			wVersionRequested = MAKEWORD(2, 2);
			if (WSAStartup(wVersionRequested, &wsaData) != 0)
				return;		// failure to start winsock
			mic_cleanup = 1;
		}
#endif
		mic_socket = socket(PF_INET, SOCK_DGRAM, 0);
		if (mic_socket != INVALID_SOCKET) {
			Addr.sin_family = AF_INET;
// This is the UDP port for TX microphone samples, and must agree with the microcontroller.
			Addr.sin_port = htons(quisk_sound_state.tx_audio_port);
#ifdef MS_WINDOWS
			Addr.sin_addr.S_un.S_addr = inet_addr(quisk_sound_state.mic_ip);
#else
			inet_aton(quisk_sound_state.mic_ip, &Addr.sin_addr);
#endif
			if (connect(mic_socket, (const struct sockaddr *)&Addr, sizeof(Addr)) != 0) {
				close(mic_socket);
				mic_socket = INVALID_SOCKET;
			}
		}
	}
}

void quisk_set_tx_mode(void)	// called when the mode rxMode is changed
{
	tx_filter(NULL, 0);
	tx_filter2(NULL, 0);
#ifdef TEST_TX_WAV_FILE
	if (!wavFp)			// convenient place to open file
		open_wav();
#endif
}

PyObject * quisk_set_spot_mode(PyObject * self, PyObject * args)
{
	if (!PyArg_ParseTuple (args, "i", &spotMode))
		return NULL;
	if (spotMode == 0)
		transmit_udp(NULL, 0);		// initialization
	Py_INCREF (Py_None);
	return Py_None;
}

PyObject * quisk_set_tx_filters(PyObject * self, PyObject * args)
{  // Enter the coefficients of the I, Q and H digital filters for transmit audio.
   // Storage space is malloc'd.
	PyObject * filterI, * filterQ, * filterC;
	int i, size;
	PyObject * obj;

	if (!PyArg_ParseTuple (args, "OOO", &filterI, &filterQ, &filterC))
		return NULL;

    if (txFilterI) {
        free (txFilterI);
        free (txFilterQ);
        free (txFilterC);
        free (txFilterBufI);
        free (txFilterBufQ);
		free (txFilterBufC);
        txFilterI = NULL;
	    txFilterIQSize = 0;
		txFilterCSize = 0;
    }
	if (PySequence_Check(filterI) != 1) {
		PyErr_SetString (PyExc_TypeError, "Filter I is not a sequence");
		return NULL;
	}
	if (PySequence_Check(filterQ) != 1) {
		PyErr_SetString (PyExc_TypeError, "Filter Q is not a sequence");
		return NULL;
	}
	if (PySequence_Check(filterC) != 1) {
		PyErr_SetString (PyExc_TypeError, "Filter C is not a sequence");
		return NULL;
	}
	size = PySequence_Size(filterI);
	if (size != PySequence_Size(filterQ)) {
		PyErr_SetString (PyExc_RuntimeError, "The size of filters I and Q must be equal");
		return NULL;
	}
	txFilterI = (double *)malloc(size * sizeof(double));
	txFilterQ = (double *)malloc(size * sizeof(double));
	txFilterBufI = (double *)malloc(size * sizeof(double));
	txFilterBufQ = (double *)malloc(size * sizeof(double));
	for (i = 0; i < size; i++) {
		obj = PySequence_GetItem(filterI, i);
		txFilterI[i] = PyFloat_AsDouble(obj);
		Py_XDECREF(obj);
		obj = PySequence_GetItem(filterQ, i);
		txFilterQ[i] = PyFloat_AsDouble(obj);
		Py_XDECREF(obj);
	}
	txFilterIQSize = size;
	size = PySequence_Size(filterC);
    if (size > 0) {
		txFilterC = (double *)malloc(size * sizeof(double));
		txFilterBufC = (complex *)malloc(size * sizeof(complex));
		for (i = 0; i < size; i++) {
			obj = PySequence_GetItem(filterC, i);
			txFilterC[i] = PyFloat_AsDouble(obj);
			Py_XDECREF(obj);
		}
	}
	txFilterCSize = size;
	Py_INCREF (Py_None);
	return Py_None;
}
