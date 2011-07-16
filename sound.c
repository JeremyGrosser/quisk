/*
 * Sound modules that do not depend on alsa or portaudio
*/
#include <Python.h>
#include <complex.h>
#include <math.h>
#include <sys/time.h>
#include <time.h>
#include "quisk.h"

#define DEBUG			0

// Thanks to Franco Spinelli for this fix:
// The H101 hardware using the PCM2904 chip has a one-sample delay between
// channels that must be fixed in software.  If you have this problem,
// set channel_delay in your config file.  The FIX_H101 #define is obsolete
// but still works.  It is equivalent to channel_delay = channel_q.

// The structure sound_dev represents a sound device to open.  If portaudio_index
// is -1, it is an ALSA sound device; otherwise it is a portaudio device with that
// index.  Portaudio devices have names that start with "portaudio".  A device name
// can be the null string, meaning the device should not be opened.  The sound_dev
// "handle" is either an alsa handle or a portaudio stream if the stream is open;
// otherwise it is NULL for a closed device.

static struct sound_dev Capture, Playback, MicCapture, MicPlayback;

QUISK_EXPORT struct sound_conf quisk_sound_state;	// Current sound status

QUISK_EXPORT ty_sample_start pt_sample_start;
QUISK_EXPORT ty_sample_stop  pt_sample_stop;
QUISK_EXPORT ty_sample_read  pt_sample_read;

static complex cSamples[SAMP_BUFFER_SIZE];			// Complex buffer for samples

void ptimer(int counts)	// used for debugging
{	// print the number of counts per second
	static unsigned int calls=0, total=0;
	static time_t time0=0;
	time_t dt;

	if (time0 == 0) {
		time0 = (int)(QuiskTimeSec() * 1.e6);
		return;
	}
	total += counts;
	calls++;
	if (calls % 1000 == 0) {
		dt = (int)(QuiskTimeSec() * 1.e6) - time0;
		printf("ptimer: %d counts in %d microseconds %.3f counts/sec\n",
			total, (unsigned)dt, (double)total * 1E6 / dt); 
	}
}

static void delay_sample (struct sound_dev * dev, double * dSamp, int nSamples)
{	// Delay the I or Q data stream by one sample.
	// cSamples is double D[nSamples][2]
	double d;
	double * first, * last;

	if (nSamples < 1)
		return;
	if (dev->channel_Delay == dev->channel_I) {
		first = dSamp;
		last = dSamp + nSamples * 2 - 2;
	}
	else if (dev->channel_Delay == dev->channel_Q) {
		first = dSamp + 1;
		last = dSamp + nSamples * 2 - 1;
	}
	else {
		return;
	}
	d = dev->save_sample;
	dev->save_sample = *last;
	while (--nSamples) {
		*last = *(last - 2);
		last -= 2;
	}
	*first = d;
}

static void correct_sample (struct sound_dev * dev, complex * cSamples, int nSamples)
{	// Correct the amplitude and phase
	int i;
	double re, im;

	if (dev->doAmplPhase) {				// amplitude and phase corrections
		for (i = 0; i < nSamples; i++) {
			re = creal(cSamples[i]);
			im = cimag(cSamples[i]);
			re = re * dev->AmPhAAAA;
			im = re * dev->AmPhCCCC + im * dev->AmPhDDDD;
			cSamples[i] = re + I * im;
		}
	}
}

int quisk_read_sound(void)	// Called from sound thread
{  // called in an infinite loop by the main program
	int i, j, k, nSamples, mic_count, retval, is_cw;
	complex acc, tx_mic_phase;
	static double cwEnvelope=0;
	static double cwCount=0;
	static complex tuneVector = (double)CLIP32 / CLIP16;	// Convert 16-bit to 32-bit samples
	static int indexInterpFilter = 0;		// index into interpolation filter
	static complex interpFilterBuf[INTERP_FILTER_TAPS];		// Interpolation audio filter

	quisk_sound_state.interupts++;

	if (pt_sample_read) {			// read samples from SDR-IQ
		nSamples = (*pt_sample_read)(cSamples);
	}
	else if (quisk_use_rx_udp) {	// read samples from UDP port
		nSamples = quisk_read_rx_udp(cSamples);
	}
	else if (Capture.handle) {							// blocking read from soundcard
		if (Capture.portaudio_index < 0)
			nSamples = quisk_read_alsa(&Capture, cSamples);
		else
			nSamples = quisk_read_portaudio(&Capture, cSamples);
		if (Capture.channel_Delay >= 0)	// delay the I or Q channel by one sample
			delay_sample(&Capture, (double *)cSamples, nSamples);
		if (Capture.doAmplPhase)		// amplitude and phase corrections
			correct_sample(&Capture, cSamples, nSamples);
	}
	else {
		nSamples = 0;
	}
	retval = nSamples;		// retval remains the number of samples read
#if DEBUG > 1
	ptimer (nSamples);
#endif
	quisk_sound_state.latencyCapt = nSamples;	// samples available
	nSamples = quisk_process_samples(cSamples, nSamples);	// get sound to play
	if (Playback.portaudio_index < 0)
		quisk_play_alsa(&Playback, nSamples, cSamples, 1);
	else
		quisk_play_portaudio(&Playback, nSamples, cSamples, 1);

	// Read and process the microphone
	mic_count = 0;
	if (MicCapture.handle) {
		if (MicCapture.portaudio_index < 0)
			mic_count = quisk_read_alsa(&MicCapture, cSamples);
		else
			mic_count = quisk_read_portaudio(&MicCapture, cSamples);
		if (mic_count > 0)
			quisk_process_microphone(cSamples, mic_count);
	}
	// Mic playback without a mic is needed for CW
	if (MicPlayback.handle) {		// Mic playback: send mic I/Q samples to a sound card
		if (rxMode == 0 || rxMode == 1) {	// Transmit CW
			is_cw = 1;
		}
		else {
			is_cw = 0;
			cwCount = 0;
			cwEnvelope = 0.0;
		}
		tx_mic_phase = cexp(( -I * 2.0 * M_PI * quisk_tx_tune_freq) / MicPlayback.sample_rate);
		if (is_cw) {	// Transmit CW; use capture device for timing, not microphone
			cwCount += (double)retval * MicPlayback.sample_rate / quisk_sound_state.sample_rate;
			mic_count = 0;
			if (quisk_is_key_down()) {
				while (cwCount >= 1.0) {
					if (cwEnvelope < 1.0) {
						cwEnvelope += 1. / (MicPlayback.sample_rate * 5e-3);	// 5 milliseconds
						if (cwEnvelope > 1.0)
							cwEnvelope = 1.0;
					}
					cSamples[mic_count++] = (CLIP16 - 1) * cwEnvelope * tuneVector * quisk_sound_state.mic_out_volume;
					tuneVector *= tx_mic_phase;
					cwCount -= 1;
				}
			}
			else {		// key is up
				while (cwCount >= 1.0) {
					if (cwEnvelope > 0.0) {
						cwEnvelope -= 1.0 / (MicPlayback.sample_rate * 5e-3);	// 5 milliseconds
						if (cwEnvelope < 0.0)
							cwEnvelope = 0.0;
					}
					cSamples[mic_count++] = (CLIP16 - 1) * cwEnvelope * tuneVector * quisk_sound_state.mic_out_volume;
					tuneVector *= tx_mic_phase;
					cwCount -= 1;
				}
			}
		}
		else if (MicCapture.handle) {		// Transmit SSB
			if ( ! quisk_is_key_down()) {
				for (i = 0; i < mic_count; i++)
					cSamples[i] = 0.0;
			}
		}
		// Perhaps interpolate the mic samples back to the mic play rate
		if ( ! is_cw && quisk_sound_state.mic_interp > 1) {
			k = quisk_sound_state.mic_interp;
			// from samples a, b, c  make  a, 0, 0, b, 0, 0, c, 0, 0
			mic_count *= k;
			for (i = mic_count - 1; i >= 0; i--) {
				if (i % k == 0)
					cSamples[i] = cSamples[i / k] * k;
				else
					cSamples[i] = 0;
			}
			for (i = 0; i < mic_count; i++) {	// low pass filter
				interpFilterBuf[indexInterpFilter] =  cSamples[i];
				acc = 0;
				j = indexInterpFilter;
				for (k = 0; k < INTERP_FILTER_TAPS; k++) {
					acc += interpFilterBuf[j] * interpFilterCoef[k];
					if (++j >= INTERP_FILTER_TAPS)
						j = 0;
				}
				cSamples[i] = acc;
				if (++indexInterpFilter >= INTERP_FILTER_TAPS)
					indexInterpFilter = 0;
			}
		}
		// Tune the samples to frequency
		if ( ! is_cw) {
			for (i = 0; i < mic_count; i++) {
				cSamples[i] = conj(cSamples[i]) * tuneVector * quisk_sound_state.mic_out_volume;
				tuneVector *= tx_mic_phase;
			}
		}
		// delay the I or Q channel by one sample
		if (MicPlayback.channel_Delay >= 0)
			delay_sample(&MicPlayback, (double *)cSamples, mic_count);
		// amplitude and phase corrections
		if (MicPlayback.doAmplPhase)
			correct_sample (&MicPlayback, cSamples, mic_count);
		// play mic samples
		if (MicPlayback.portaudio_index < 0)
			quisk_play_alsa(&MicPlayback, mic_count, cSamples, 0);
		else
			quisk_play_portaudio(&MicPlayback, mic_count, cSamples, 0);
	}
	// Return negative number for error
	return retval;
}

int quisk_get_overrange(void)	// Called from GUI thread
{  // Return the overrange (ADC clip) counter, then zero it
	int i;

	i = quisk_sound_state.overrange + Capture.overrange;
	quisk_sound_state.overrange = 0;
	Capture.overrange = 0;
	return i;
}

void quisk_close_sound(void)	// Called from sound thread
{
	if (pt_sample_stop)
		(*pt_sample_stop)();
	quisk_close_sound_portaudio();
	quisk_close_sound_alsa(&Capture, &Playback, &MicCapture, &MicPlayback);
	Capture.handle = NULL;
	Playback.handle = NULL;
	MicCapture.handle = NULL;
	MicPlayback.handle = NULL;
	strncpy (quisk_sound_state.err_msg, CLOSED_TEXT, QUISK_SC_SIZE);
}

static void set_num_channels(struct sound_dev * dev)
{	// Set num_channels to the maximum channel index plus one
	dev->num_channels = dev->channel_I;
	if (dev->num_channels < dev->channel_Q)
		dev->num_channels = dev->channel_Q;
	dev->num_channels++;
}

void quisk_set_decimation(void)		// Set the decimation rates
{
	int idecim, sample, play;
	double d;

	sample = quisk_sound_state.sample_rate;
	play   = quisk_sound_state.playback_rate;
	if (sample == play) {		// typical for sound card
		if (sample % 48000 == 0) {	// filter at 48 kHz
			idecim = sample / 48000;
			quisk_sound_state.int_filter_decim = idecim;
			quisk_sound_state.int_filter_interp = idecim;
			quisk_sound_state.double_filter_decim = 1.0;
		}
		else {	// No decimation
			quisk_sound_state.int_filter_decim = 1;
			quisk_sound_state.int_filter_interp = 1;
			quisk_sound_state.double_filter_decim = 1.0;
		}
	}
	else {
		quisk_sound_state.int_filter_interp = 1;
		// Sample rate might be a near-multiple of play rate, but adjusted to an
		// exact crystal frequency.  Allow for slight changes in sample_rate to
		// correct the crystal frequency.
		idecim = sample / (play - 10);
		quisk_sound_state.int_filter_decim = idecim;
		d = (double)sample / play / idecim;
		if (fabs(d - 1.0) < 200e-6)
			d = 1.0;
		quisk_sound_state.double_filter_decim = d;
	}
#if DEBUG
	printf("int_filter_decim %d, int_filter_interp %d, double_filter_decim %.3f\n",
		quisk_sound_state.int_filter_decim,	quisk_sound_state.int_filter_interp,
		quisk_sound_state.double_filter_decim);
#endif
}

void quisk_open_sound(void)	// Called from GUI thread
{
	int i;

	quisk_sound_state.read_error = 0;
	quisk_sound_state.write_error = 0;
	quisk_sound_state.underrun_error = 0;
	quisk_sound_state.mic_read_error = 0;
	quisk_sound_state.interupts = 0;
	quisk_sound_state.rate_min = quisk_sound_state.rate_max = -99;
	quisk_sound_state.chan_min = quisk_sound_state.chan_max = -99;
	quisk_sound_state.msg1[0] = 0;
	quisk_sound_state.err_msg[0] = 0;

	strncpy(Capture.name, quisk_sound_state.dev_capt_name, QUISK_SC_SIZE);
	strncpy(Playback.name, quisk_sound_state.dev_play_name, QUISK_SC_SIZE);
	strncpy(MicCapture.name, quisk_sound_state.mic_dev_name, QUISK_SC_SIZE);
	strncpy(MicPlayback.name, quisk_sound_state.name_of_mic_play, QUISK_SC_SIZE);
	Playback.sample_rate = quisk_sound_state.playback_rate;		// Radio sound play rate
	MicPlayback.sample_rate = quisk_sound_state.mic_playback_rate;
	MicCapture.sample_rate = quisk_sound_state.mic_sample_rate;
	MicCapture.channel_I = quisk_sound_state.mic_channel_I;	// Mic audio is here
	MicCapture.channel_Q = quisk_sound_state.mic_channel_Q;

	set_num_channels (&Capture);
	set_num_channels (&Playback);
	set_num_channels (&MicCapture);
	set_num_channels (&MicPlayback);

#ifdef FIX_H101
	Capture.channel_Delay = Capture.channel_Q;	// Obsolete; do not use.
#else
	Capture.channel_Delay = QuiskGetConfigLong ("channel_delay", -1);
#endif
	MicPlayback.channel_Delay = QuiskGetConfigLong ("tx_channel_delay", -1);

	if (pt_sample_read) {		// capture from SDR-IQ by Rf-Space
		Capture.name[0] = 0;	// zero the capture soundcard name
    }
	else if (quisk_use_rx_udp) {	// samples from UDP at multiple of 48 kHz
		Capture.name[0] = 0;		// zero the capture soundcard name
    }
	else {		// sound card capture
		Capture.sample_rate = quisk_sound_state.sample_rate;
	}
	quisk_set_decimation();
	// see if we need to interpolate the mic samples before playing
	quisk_sound_state.mic_interp = 1;	// Mic interpolation must be an integer
	if (MicPlayback.name[0] && MicCapture.name[0])
		quisk_sound_state.mic_interp = MicPlayback.sample_rate / MicCapture.sample_rate;
	// set read size for sound card capture
	i = (int)(quisk_sound_state.data_poll_usec * 1e-6 * Capture.sample_rate + 0.5);
	i = i / 64 * 64;
	if (i > SAMP_BUFFER_SIZE / Capture.num_channels)		// limit to buffer size
		i = SAMP_BUFFER_SIZE / Capture.num_channels;
	Capture.read_frames = i;
	MicCapture.read_frames = 0;		// Use non-blocking read for microphone
	Playback.read_frames = 0;
	MicPlayback.read_frames = 0;
	// set sound card play latency
	Playback.latency_frames = Playback.sample_rate * quisk_sound_state.latency_millisecs / 1000;
	MicPlayback.latency_frames = MicPlayback.sample_rate * quisk_sound_state.latency_millisecs / 1000;
	Capture.latency_frames = 0;
	MicCapture.latency_frames = 0;
#if DEBUG
	printf("Sample buffer size %d\n", SAMP_BUFFER_SIZE);
	printf ("mic interpolation %d\n", quisk_sound_state.mic_interp);
#endif
}

void quisk_start_sound(void)	// Called from sound thread
{
	if (pt_sample_start)
		(*pt_sample_start)();
	quisk_start_sound_portaudio(&Capture, &Playback, &MicCapture, &MicPlayback);
	quisk_start_sound_alsa(&Capture, &Playback, &MicCapture, &MicPlayback);
	if (pt_sample_read || quisk_use_rx_udp) {
		quisk_sound_state.rate_min = Playback.rate_min;
		quisk_sound_state.rate_max = Playback.rate_max;
		quisk_sound_state.chan_min = Playback.chan_min;
		quisk_sound_state.chan_max = Playback.chan_max;
	}
	else {
		quisk_sound_state.rate_min = Capture.rate_min;
		quisk_sound_state.rate_max = Capture.rate_max;
		quisk_sound_state.chan_min = Capture.chan_min;
		quisk_sound_state.chan_max = Capture.chan_max;
	}
}

PyObject * quisk_set_ampl_phase(PyObject * self, PyObject * args)	// Called from GUI thread
{  /*	Set the sound card amplitude and phase corrections.  See
	S.W. Ellingson, Correcting I-Q Imbalance in Direct Conversion Receivers, February 10, 2003 */
	struct sound_dev * dev;
	double ampl, phase;
	int is_tx;		// Is this for Tx?  Otherwise Rx.

	if (!PyArg_ParseTuple (args, "ddi", &ampl, &phase, &is_tx))
		return NULL;
	if (is_tx)
		dev = &MicPlayback;
	else
		dev = &Capture;
	if (ampl == 0.0 && phase == 0.0) {
		dev->doAmplPhase = 0;
	}
	else {
		dev->doAmplPhase = 1;
		ampl = ampl + 1.0;			// Change factor 0.01 to 1.01
		phase = (phase / 360.0) * 2.0 * M_PI;	// convert to radians
		dev->AmPhAAAA = 1.0 / ampl;
		dev->AmPhCCCC = - dev->AmPhAAAA * tan(phase);
		dev->AmPhDDDD = 1.0 / cos(phase);
	}
	Py_INCREF (Py_None);
	return Py_None;
}

PyObject * quisk_capt_channels(PyObject * self, PyObject * args)	// Called from GUI thread
{
	if (!PyArg_ParseTuple (args, "ii", &Capture.channel_I, &Capture.channel_Q))
		return NULL;
	Py_INCREF (Py_None);
	return Py_None;
}

PyObject * quisk_play_channels(PyObject * self, PyObject * args)	// Called from GUI thread
{
	if (!PyArg_ParseTuple (args, "ii", &Playback.channel_I, &Playback.channel_Q))
		return NULL;
	Py_INCREF (Py_None);
	return Py_None;
}

PyObject * quisk_micplay_channels(PyObject * self, PyObject * args)	// Called from GUI thread
{
	if (!PyArg_ParseTuple (args, "ii", &MicPlayback.channel_I, &MicPlayback.channel_Q))
		return NULL;
	Py_INCREF (Py_None);
	return Py_None;
}
