/*
 * This modue provides sound access for QUISK using the portaudio library.
*/
#include <Python.h>
#include <complex.h>
#include <math.h>
#include <portaudio.h>
#include <sys/time.h>
#include <time.h>
#include "quisk.h"

#define DEBUG		0

/*
 The sample rate is in frames per second.  Each frame has a number of channels,
 and each channel has a sample of size sample_bytes.  The channels are interleaved:
 (channel0, channel1), (channel0, channel1), ...
*/

extern struct sound_conf quisk_sound_state;	// Current sound status

static float fbuffer[SAMP_BUFFER_SIZE];		// Buffer for float32 samples from sound

int quisk_read_portaudio(struct sound_dev * dev, complex * cSamples)
{	// Read sound samples from the soundcard.
	// Samples are converted to 32 bits with a range of +/- CLIP32 and placed into cSamples.
	int i;
	long avail;
	int nSamples;
	complex c;
	PaError error;
	float fi, fq;

	if (!dev->handle)
		return -1;

	avail = dev->read_frames;		// size of read request
	if (avail == 0) {				// non-blocking: read available frames
		avail = Pa_GetStreamReadAvailable((PaStream * )dev->handle);
		if (avail > SAMP_BUFFER_SIZE / dev->num_channels)		// limit read request to buffer size
			avail = SAMP_BUFFER_SIZE / dev->num_channels;
	}
	error = Pa_ReadStream ((PaStream * )dev->handle, fbuffer, avail);
	if (error != paNoError)
		quisk_sound_state.read_error++;
	nSamples = 0;
	for (i = 0; avail; i += dev->num_channels, nSamples++, avail--) {
		fi = fbuffer[i + dev->channel_I];
		fq = fbuffer[i + dev->channel_Q];
		if (fi >=  1.0 || fi <= -1.0)
			dev->overrange++;	// assume overrange returns max int
		if (fq >=  1.0 || fq <= -1.0)
			dev->overrange++;
		cSamples[nSamples] = (fi + I * fq) * CLIP32;
	}
	for (i = 0; i < nSamples; i++) {	// DC removal; R.G. Lyons page 553
		c = cSamples[i] + dev->dc_remove * 0.95;
		cSamples[i] = c - dev->dc_remove;
		dev->dc_remove = c;
	}
	return nSamples;
}

void quisk_play_portaudio(struct sound_dev * playdev, int nSamples, complex * cSamples,
		int report_latency)
{	// play the samples; write them to the portaudio soundcard
	int i, n, index;
	long delay;
	float fi, fq;
	PaError error;

	if (!playdev->handle || nSamples <= 0)
		return;

	// "delay" is the number of samples left in the play buffer
	delay = playdev->play_buf_size - Pa_GetStreamWriteAvailable(playdev->handle);
	//printf ("play available %ld\n", Pa_GetStreamWriteAvailable(playdev->handle));
	if (report_latency) {		// Report for main playback device
		quisk_sound_state.latencyPlay = delay;
	}
//printf ("nSamples %d, delay %ld\n", nSamples, delay);
	index = 0;
	if (nSamples + delay > playdev->latency_frames) {		// too many samples
		index = nSamples + delay - playdev->latency_frames;	// write only the most recent samples
		if (index > nSamples)
			index = nSamples;
		quisk_sound_state.write_error++;
#if DEBUG
		printf("Discard %d of %d samples at %d delay\n", index, nSamples, (int)delay);
#endif
		if (nSamples == index)		// no samples to play
			return;
	}
	else if (delay < 16) {		// Buffer is too empty; fill it back up with zeros.
		n = playdev->latency_frames * 7 / 8 - nSamples;
#if DEBUG
		printf("Add %d zero samples at %ld delay\n", n, delay);
#endif
		for (i = 0; i < n; i++)
			cSamples[nSamples++] = 0;
	}
	for (i = 0, n = index; n < nSamples; i += playdev->num_channels, n++) {
		fi = creal(cSamples[n]);
		fq = cimag(cSamples[n]);
		fbuffer[i + playdev->channel_I] = fi / CLIP32;
		fbuffer[i + playdev->channel_Q] = fq / CLIP32;
	}
	error = Pa_WriteStream ((PaStream * )playdev->handle, fbuffer, nSamples - index);
//printf ("Write %d\n", nSamples - index);
	if (error == paNoError)
		;
	else if (error == paOutputUnderflowed)
		quisk_sound_state.underrun_error++;
	else {
		quisk_sound_state.write_error++;
#if DEBUG
		printf ("Play error: %s\n", Pa_GetErrorText(error));
#endif
	}
}

static void info_portaudio (struct sound_dev * cDev, struct sound_dev * pDev)
{	// Return information about the device
	const PaDeviceInfo * info;
	PaStreamParameters params;
	int index, rate;

	if (cDev)
		index = cDev->portaudio_index;
	else if (pDev)
		index = pDev->portaudio_index;
	else
		return;
	info = Pa_GetDeviceInfo(index);
	if ( ! info)
		return;

	params.device = index;
	params.channelCount = 1;
	params.sampleFormat = paFloat32;
	params.suggestedLatency = 0.10;
	params.hostApiSpecificStreamInfo = NULL;

	if (cDev) {
		cDev->chan_min = 1;
		cDev->chan_max = info->maxInputChannels;
		cDev->rate_min = cDev->rate_max = 0;
		cDev->portaudio_latency = info->defaultHighInputLatency;
#if DEBUG
		printf ("Capture latency low %lf,  high %lf\n",
				info->defaultLowInputLatency, info->defaultHighInputLatency);
#endif
		for (rate = 8000; rate <= 384000; rate += 8000) {
			if (Pa_IsFormatSupported(&params, NULL, rate) == paFormatIsSupported) {
				if (cDev->rate_min == 0)
					cDev->rate_min = rate;
				cDev->rate_max = rate;
			}
		}
	}

	if (pDev) {
		pDev->chan_min = 1;
		pDev->chan_max = info->maxOutputChannels;
		pDev->rate_min = pDev->rate_max = 0;
		pDev->portaudio_latency = quisk_sound_state.latency_millisecs / 1000.0 * 2.0;
		if (pDev->portaudio_latency < info->defaultHighOutputLatency)
			pDev->portaudio_latency = info->defaultHighOutputLatency;
#if DEBUG
		printf ("Play latency low %lf,  high %lf\n",
				info->defaultLowOutputLatency, info->defaultHighOutputLatency);
#endif
		for (rate = 8000; rate <= 384000; rate += 8000) {
			if (Pa_IsFormatSupported(&params, NULL, rate) == paFormatIsSupported) {
				if (pDev->rate_min == 0)
					pDev->rate_min = rate;
				pDev->rate_max = rate;
			}
		}
	}
}

static int quisk_pa_name2index (struct sound_dev * dev, int is_capture)
{	// Based on the device name, set the portaudio index, or -1.
	// Return non-zero for error.  Not a portaudio device is not an error.
	const PaDeviceInfo * pInfo;
	int i, count;

	if (strncmp (dev->name, "portaudio", 9)) {
		dev->portaudio_index = -1;	// Name does not start with "portaudio"
		return 0;		// Not a portaudio device, not an error
	}
	if ( ! strcmp (dev->name, "portaudiodefault")) {
		if (is_capture)		// Fill in the default device index
			dev->portaudio_index = Pa_GetDefaultInputDevice();
		else
			dev->portaudio_index = Pa_GetDefaultOutputDevice();
		strncpy (dev->msg1, "Using default portaudio device", QUISK_SC_SIZE);
		return 0;
	}
	if ( ! strncmp (dev->name, "portaudio#", 10)) {		// Integer index follows "#"
		dev->portaudio_index = i = atoi(dev->name + 10);
		pInfo = Pa_GetDeviceInfo(i);
		if (pInfo) {
			snprintf (dev->msg1, QUISK_SC_SIZE, "PortAudio device %s",  pInfo->name);
			return 0;
		}
		else {
			snprintf (quisk_sound_state.err_msg, QUISK_SC_SIZE,
				"Can not find portaudio device number %s", dev->name + 10);
		}
		return 1;
	}
	if ( ! strncmp (dev->name, "portaudio:", 10)) {
		dev->portaudio_index = -1;
		count = Pa_GetDeviceCount();		// Search for string in device name
		for (i = 0; i < count; i++) {
			pInfo = Pa_GetDeviceInfo(i);
			if (pInfo && strstr(pInfo->name, dev->name + 10)) {
				dev->portaudio_index = i;
				snprintf (dev->msg1, QUISK_SC_SIZE, "PortAudio device %s",  pInfo->name);
				break;
			}
		}
		if (dev->portaudio_index == -1)	{	// Error
			snprintf (quisk_sound_state.err_msg, QUISK_SC_SIZE,
				"Can not find portaudio device named %s", dev->name + 10);
			return 1;
		}
		return 0;
	}
	snprintf (quisk_sound_state.err_msg, QUISK_SC_SIZE,
		"Did not recognize portaudio device %s", dev->name);
	return 1;
}

static int quisk_open_portaudio (struct sound_dev * cDev, struct sound_dev * pDev)
{	// Open the portaudio soundcard for capture on cDev and playback on pDev (or NULL).
	// Return non-zero for error.
	PaStreamParameters cParams, pParams;
	PaError error;
	PaStream * hndl;

	info_portaudio (cDev, pDev);

	if (pDev && cDev && pDev->sample_rate != cDev->sample_rate) {
		strncpy(quisk_sound_state.err_msg, "Capture and Play sample rates must be equal.", QUISK_SC_SIZE);
		return 1;
	}

	cParams.sampleFormat = paFloat32;
	pParams.sampleFormat = paFloat32;
	cParams.hostApiSpecificStreamInfo = NULL;
	pParams.hostApiSpecificStreamInfo = NULL;

	if (cDev) {
		cDev->handle = NULL;
		cParams.device = cDev->portaudio_index;
		cParams.channelCount = cDev->num_channels;
		cParams.suggestedLatency = cDev->portaudio_latency;
	}

	if (pDev) {
		pDev->handle = NULL;
		pParams.device = pDev->portaudio_index;
		pParams.channelCount = pDev->num_channels;
		pParams.suggestedLatency = pDev->portaudio_latency;
	}

	if (cDev && pDev) {
		error = Pa_OpenStream (&hndl, &cParams, &pParams,
				(double)cDev->sample_rate, cDev->read_frames, 0, NULL, NULL);
		pDev->handle = cDev->handle = (void *)hndl;

	}
	else if (cDev) {
		error = Pa_OpenStream (&hndl, &cParams, NULL,
				(double)cDev->sample_rate, cDev->read_frames, 0, NULL, NULL);
		cDev->handle = (void *)hndl;
	}
	else if (pDev) {
		error = Pa_OpenStream (&hndl, NULL, &pParams,
				(double)pDev->sample_rate, 0, 0, NULL, NULL);
		pDev->handle = (void *)hndl;
	}
	else {
		error = paNoError;
	}
	if (pDev) {
		pDev->play_buf_size = Pa_GetStreamWriteAvailable(pDev->handle);
		if (pDev->latency_frames > pDev->play_buf_size) {
#if DEBUG
			printf("Latency frames %d limited to buffer size %d\n",
					pDev->latency_frames, pDev->play_buf_size);
#endif
			pDev->latency_frames = pDev->play_buf_size;
		}
	}
#if DEBUG
	printf ("play_buf_size %d\n", pDev->play_buf_size);
#endif
	if (error == paNoError)
		return 0;
	strncpy(quisk_sound_state.err_msg, Pa_GetErrorText(error), QUISK_SC_SIZE);
	return 1;
}

void quisk_start_sound_portaudio(struct sound_dev * pCapture, struct sound_dev * pPlayback,
		struct sound_dev * pMicCapture, struct sound_dev * pMicPlayback)
{
	int index, err;

	Pa_Initialize();
	// Set the portaudio index from the name; or set -1.  Return on error.
	if (quisk_pa_name2index (pCapture, 1))
		return;		// Error
	if (quisk_pa_name2index (pPlayback, 0))
		return;
	if (quisk_pa_name2index (pMicCapture, 1))
		return;
	if (quisk_pa_name2index (pMicPlayback, 0))
		return;

	// Open the sound cards
	index = pCapture->portaudio_index;
	if (index >= 0) {		// This is a portaudio device
		if (pPlayback->portaudio_index == index)			// same device
			err = quisk_open_portaudio (pCapture, pPlayback);
		else if (pMicPlayback->portaudio_index == index)	// same device
			err = quisk_open_portaudio (pCapture, pMicPlayback);
		else
			err = quisk_open_portaudio (pCapture, NULL);		// no matching device
		if (err)
			return;		// error
		strncpy (quisk_sound_state.msg1, pCapture->msg1, QUISK_SC_SIZE);
	}
	index = pMicCapture->portaudio_index;
	if (index >= 0) {		// This is a portaudio device
		if (pPlayback->portaudio_index == index)			// same device
			err = quisk_open_portaudio (pMicCapture, pPlayback);
		else if (pMicPlayback->portaudio_index == index)	// same device
			err = quisk_open_portaudio (pMicCapture, pMicPlayback);
		else
			err = quisk_open_portaudio (pMicCapture, NULL);		// no matching device
		if (err)
			return;		// error
	}
	// Open remaining portaudio devices
	if (pPlayback->portaudio_index >= 0 && ! pPlayback->handle) {
		if (quisk_open_portaudio (NULL, pPlayback))
			return;		// error
        if ( ! quisk_sound_state.msg1[0])
			strncpy (quisk_sound_state.msg1, pPlayback->msg1, QUISK_SC_SIZE);
	}
	if (pMicPlayback->portaudio_index >= 0 && ! pMicPlayback->handle)
		if (quisk_open_portaudio (NULL, pMicPlayback))
			return;		// error
	if (pCapture->handle)
		Pa_StartStream((PaStream * )pCapture->handle);
	if (pMicCapture->handle)
		Pa_StartStream((PaStream * )pMicCapture->handle);
	if (pPlayback->handle && Pa_IsStreamStopped((PaStream * )pPlayback->handle))
		Pa_StartStream((PaStream * )pPlayback->handle);
	if (pMicPlayback->handle && Pa_IsStreamStopped((PaStream * )pMicPlayback->handle))
		Pa_StartStream((PaStream * )pMicPlayback->handle);
}

void quisk_close_sound_portaudio(void)
{
	Pa_Terminate();
}
