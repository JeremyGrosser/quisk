#include <Python.h>
#include <complex.h>
#include <math.h>
#include "quisk.h"
#include "Dsound.h"
//#include <audiodefs.h>
#include <Mmreg.h>
//#include <ksmedia.h>
//#include <uuids.h>


// This module provides sound card access using Direct Sound

#define DEBUG		0

HRESULT errFound, errOpen;

static GUID IEEE = {0x00000003, 0x0000, 0x0010, {0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71}};
static GUID PCMM = {0x00000001, 0x0000, 0x0010, {0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71}};

static BOOL CALLBACK DSEnumNames(LPGUID lpGUID, LPCTSTR lpszDesc, LPCTSTR lpszDrvName, LPVOID pyseq)
{
	PyList_Append((PyObject *)pyseq, PyString_FromString(lpszDesc));
	return( TRUE );
}

static BOOL CALLBACK DsEnumPlay(LPGUID lpGUID, LPCTSTR lpszDesc, LPCTSTR lpszDrvName, LPVOID dev)
{	// Open the play device if the name is found in the description
	LPDIRECTSOUND8 DsDev;

	if (strstr (lpszDesc, ((struct sound_dev *)dev)->name)) {
		errFound = DS_OK;
		errOpen = DirectSoundCreate8(lpGUID, &DsDev, NULL);
		if (errOpen == DS_OK) {
			((struct sound_dev *)dev)->handle = DsDev;
		}
		return FALSE;	// Stop iteration
	}
	else {
		return TRUE;
	}
}

static BOOL CALLBACK DsEnumCapture(LPGUID lpGUID, LPCTSTR lpszDesc, LPCTSTR lpszDrvName, LPVOID dev)
{	// Open the capture device if the name is found in the description
	LPDIRECTSOUNDCAPTURE8 DsDev;

	if (strstr (lpszDesc, ((struct sound_dev *)dev)->name)) {
		errFound = DS_OK;
		errOpen = DirectSoundCaptureCreate8(lpGUID, &DsDev, NULL);
		if (errOpen == DS_OK)
			((struct sound_dev *)dev)->handle = DsDev;
		return FALSE;	// Stop iteration
	}
	else {
		return TRUE;
	}
}

static void MakeWFext(int use_new, int use_float, struct sound_dev * dev, WAVEFORMATEXTENSIBLE * pwfex)
{	// fill in a WAVEFORMATEXTENSIBLE structure
	if (use_float)
		dev->sample_bytes = 4;
	if (use_new) {
		pwfex->Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
		pwfex->Format.cbSize = 22;
		pwfex->Samples.wValidBitsPerSample = dev->sample_bytes * 8;
		if (dev->num_channels == 1)
			pwfex->dwChannelMask = SPEAKER_FRONT_LEFT;
		else
			pwfex->dwChannelMask = SPEAKER_FRONT_LEFT | SPEAKER_FRONT_RIGHT;
		if (use_float) {
			pwfex->SubFormat = IEEE;
			dev->use_float = 1;
		}
		else {
			pwfex->SubFormat = PCMM;
			dev->use_float = 0;
		}
	}
	else {
		pwfex->Format.cbSize = 0;
		if (use_float) {
			pwfex->Format.wFormatTag = 0x03;	//WAVE_FORMAT_IEEE;
			dev->use_float = 1;
		}
		else {
			pwfex->Format.wFormatTag = WAVE_FORMAT_PCM;
			dev->use_float = 0;
		}
	}
	pwfex->Format.nChannels = dev->num_channels;
	pwfex->Format.nSamplesPerSec = dev->sample_rate;
	pwfex->Format.nAvgBytesPerSec = dev->num_channels * dev->sample_rate * dev->sample_bytes;
	dev->play_buf_size = pwfex->Format.nAvgBytesPerSec;
	pwfex->Format.nBlockAlign = dev->num_channels * dev->sample_bytes;
	pwfex->Format.wBitsPerSample = dev->sample_bytes * 8;
}

static int quisk_open_capture(struct sound_dev * dev)
{	// Open the soundcard for capture.  Return non-zero for error.
	LPDIRECTSOUNDCAPTUREBUFFER ptBuf;
	DSCBUFFERDESC dscbd;
	HRESULT hr;
	WAVEFORMATEXTENSIBLE wfex;

	dev->handle = NULL; 
	dev->buffer = NULL; 
	dev->portaudio_index = -1;
	if ( ! dev->name[0])	// Check for null play name; not an error
		return 0;
	errFound = ~DS_OK;
	DirectSoundCaptureEnumerate((LPDSENUMCALLBACK)DsEnumCapture, dev);
	if (errFound != DS_OK) {
		snprintf (quisk_sound_state.err_msg, SC_SIZE,
			"DirectSound capture device name %s not found", dev->name);
		return 1;
	}
	if (errOpen != DS_OK) {
		snprintf (quisk_sound_state.err_msg, SC_SIZE,
			"DirectSound capture device %s open failed", dev->name);
		return 1;
	}
	dev->sample_bytes = 4;
	MakeWFext (1, 0, dev, &wfex);		// fill in wfex
	memset(&dscbd, 0, sizeof(DSCBUFFERDESC));
	dscbd.dwSize = sizeof(DSCBUFFERDESC);
	dscbd.dwFlags = 0;
	dscbd.dwBufferBytes = dev->play_buf_size;	// one second buffer
	dscbd.lpwfxFormat = (WAVEFORMATEX *)&wfex;
	hr = IDirectSoundCapture_CreateCaptureBuffer(
		(LPDIRECTSOUNDCAPTURE8)dev->handle, &dscbd, &ptBuf, NULL);
	if (hr == DS_OK) {
		dev->buffer = ptBuf;
#if DEBUG
		printf("Created capture buffer size %d bytes for %s\n",
			dev->play_buf_size, dev->name);
#endif
	}
	else {
		snprintf (quisk_sound_state.err_msg, SC_SIZE,
			"DirectSound capture device %s buffer create failed (0x%lX)", dev->name, hr);
		return 1;
	}
	ptBuf = (LPDIRECTSOUNDCAPTUREBUFFER)dev->buffer;
	hr = IDirectSoundCaptureBuffer8_Start(ptBuf, DSCBSTART_LOOPING);
	if (hr != DS_OK) {
#if DEBUG
		printf("Capture start error 0x%lX", hr);
#endif
		snprintf (quisk_sound_state.err_msg, SC_SIZE,
			"DirectSound capture device %s capture start failed", dev->name);
		return 1;
	}
	return 0;
}

static int quisk_open_playback(struct sound_dev * dev)
{	// Open the soundcard for playback.  Return non-zero for error.
	LPDIRECTSOUNDBUFFER ptBuf;
	WAVEFORMATEXTENSIBLE wfex;
	DSBUFFERDESC dsbdesc; 
	HRESULT hr;

	dev->handle = NULL; 
	dev->buffer = NULL; 
	dev->portaudio_index = -1;
	dev->sample_bytes = 2;
	if ( ! dev->name[0])	// Check for null play name; not an error
		return 0;
	errFound = ~DS_OK;
	DirectSoundEnumerate((LPDSENUMCALLBACK)DsEnumPlay, dev);
	if (errFound != DS_OK) {
		snprintf (quisk_sound_state.err_msg, SC_SIZE,
			"DirectSound play device name %s not found", dev->name);
		return 1;
	}
	if (errOpen != DS_OK) {
		snprintf (quisk_sound_state.err_msg, SC_SIZE,
			"DirectSound play device %s open failed", dev->name);
		return 1;
	}
	hr = IDirectSound_SetCooperativeLevel ((LPDIRECTSOUND8)dev->handle, (HWND)quisk_mainwin_handle, DSSCL_PRIORITY);
	if (hr != DS_OK) {
		snprintf (quisk_sound_state.err_msg, SC_SIZE,
			"DirectSound play device %s cooperative level failed", dev->name);
		return 1;
	}
	dev->sample_bytes = 4;
	MakeWFext (1, 0, dev, &wfex);		// fill in wfex
	memset(&dsbdesc, 0, sizeof(DSBUFFERDESC));
	dsbdesc.dwSize = sizeof(DSBUFFERDESC); 
	dsbdesc.dwFlags = DSBCAPS_GETCURRENTPOSITION2|DSBCAPS_GLOBALFOCUS;
	dsbdesc.dwBufferBytes = dev->play_buf_size;	// one second buffer
	dsbdesc.lpwfxFormat = (LPWAVEFORMATEX)&wfex;
	hr = IDirectSound_CreateSoundBuffer(
		(LPDIRECTSOUND8)dev->handle, &dsbdesc, &ptBuf, NULL); 
	if (hr == DS_OK) {
		dev->buffer = ptBuf;
	}
	else {
		snprintf (quisk_sound_state.err_msg, SC_SIZE,
			"DirectSound play device %s buffer create failed (0x%X)", dev->name, hr);
		return 1;
	}
	return 0;
}

PyObject * quisk_sound_devices(PyObject * self, PyObject * args)
{	// Return a list of DirectSound device names
	PyObject * pylist, * pycapt, * pyplay;

	if (!PyArg_ParseTuple (args, ""))
		return NULL;

	// Each pycapt and pyplay is a device name
	pylist = PyList_New(0);		// list [pycapt, pyplay]
	pycapt = PyList_New(0);		// list of capture devices
	pyplay = PyList_New(0);		// list of play devices
	PyList_Append(pylist, pycapt);
	PyList_Append(pylist, pyplay);
	DirectSoundCaptureEnumerate((LPDSENUMCALLBACK)DSEnumNames, pycapt);
	DirectSoundEnumerate((LPDSENUMCALLBACK)DSEnumNames, pyplay);
	return pylist;
}

void quisk_start_sound_alsa (struct sound_dev * pCapture, struct sound_dev * pPlayback,
		struct sound_dev * pMicCapture, struct sound_dev * pMicPlayback)
{	// DirectX must open the playback device before the (same) capture device
	if (quisk_sound_state.err_msg[0])
		return;		// prior error
	if (quisk_open_playback(pPlayback))
		return;		// error
	if (quisk_open_playback(pMicPlayback))
		return;
	if (quisk_open_capture(pCapture))
		return;
	if (quisk_open_capture(pMicCapture))
		return;
}

void quisk_close_sound_alsa(struct sound_dev * pCapture, struct sound_dev * pPlayback,
		struct sound_dev * pMicCapture, struct sound_dev * pMicPlayback)
{
	if (pCapture->buffer)
		IDirectSoundCaptureBuffer_Stop((LPDIRECTSOUNDCAPTUREBUFFER)pCapture->buffer);
	if (pPlayback->buffer)
		IDirectSoundBuffer8_Stop((LPDIRECTSOUNDBUFFER)pPlayback->buffer);
	if (pMicCapture->buffer)
		IDirectSoundCaptureBuffer_Stop((LPDIRECTSOUNDCAPTUREBUFFER)pMicCapture->buffer);
	if (pMicPlayback->buffer)
		IDirectSoundBuffer8_Stop((LPDIRECTSOUNDBUFFER)pMicPlayback->buffer);
}


int  quisk_read_alsa(struct sound_dev * dev, complex * cSamples)
{
	LPDIRECTSOUNDCAPTUREBUFFER ptBuf = (LPDIRECTSOUNDCAPTUREBUFFER)dev->buffer;
	HRESULT hr;
	DWORD readPos, captPos;
	static DWORD dataPos=0;
	LPVOID pt1, pt2;
	DWORD i, n1, n2;
	short si, sq, * pts;
	float fi, fq, * ptf;
	long  li, lq, * ptl;
	complex c;
	int ii, qq, nSamples;
	int bytes, frames, poll_size, millisecs, bytes_per_frame, pass;
	static int started = 0;
	
	if ( ! dev->handle || ! dev->buffer)
		return 0;

	bytes_per_frame = dev->num_channels * dev->sample_bytes;
	hr = IDirectSoundCaptureBuffer8_GetCurrentPosition(ptBuf, &captPos, &readPos);
	if (hr != DS_OK) {
#if DEBUG
		printf ("Get CurrentPosition error 0x%lX\n", hr);
#endif
		quisk_sound_state.read_error++;
		return 0;
	}
// printf("dataPos %d\n", dataPos);
	if ( ! started) {
// printf("Start %d\n", started);
		dataPos = readPos;
	}
	started = 1;
	if (readPos >= dataPos)
		bytes = readPos - dataPos;
	else
		bytes = readPos - dataPos + dev->play_buf_size;
	frames = bytes / bytes_per_frame;	// frames available to read
	poll_size = (int)(quisk_sound_state.data_poll_usec * 1e-6 * dev->sample_rate + 0.5);
	millisecs = (poll_size - frames) * 1000 / dev->sample_rate;	// time to read remaining poll size
	if (millisecs > 0) {		// wait for additional frames
		Sleep(millisecs);
		hr = IDirectSoundCaptureBuffer8_GetCurrentPosition(ptBuf, &captPos, &readPos);
		if (hr != DS_OK) {
#if DEBUG
			printf ("Get CurrentPosition two error 0x%lX\n", hr);
#endif
			quisk_sound_state.read_error++;
			return 0;
		}
		if (readPos >= dataPos)
			bytes = readPos - dataPos;
		else
			bytes = readPos - dataPos + dev->play_buf_size;
	}
	frames = bytes / bytes_per_frame;	// frames available to read
	bytes = frames * bytes_per_frame;	// round to frames
	if ( ! bytes) {
		return 0;
	}
	i = poll_size * bytes_per_frame * 4;	// Limit size of read
	if (bytes > i) {
		bytes = i;
		frames = bytes / bytes_per_frame;
	}
	if (IDirectSoundCaptureBuffer8_Lock(ptBuf, dataPos, bytes, &pt1, &n1, &pt2, &n2, 0) != DS_OK) {
		quisk_sound_state.read_error++;
		return 0;
	}
//printf ("%d %d %d %d\n", dev->channel_I, dev->channel_Q, bytes_per_frame, dev->num_channels);
#if DEBUG > 2
	printf("Read %4d bytes %4d frames from %9lu to (%9lu %9lu) diff %9lu\n",
		bytes, frames, dataPos, readPos, captPos, captPos - readPos);
#endif
#if DEBUG
	if (bytes != n1 + n2)
		printf ("Lock not equal to bytes\n");
#endif
	dataPos += bytes;
	dataPos = dataPos % dev->play_buf_size;
	nSamples = 0;
	pass = 0;
	switch (dev->sample_bytes + dev->use_float) {
	case 2:
		pts = (short *)pt1;
		frames = (n1 + n2) / bytes_per_frame;
		bytes = 0;
		while (frames) {
			si = pts[dev->channel_I];
			sq = pts[dev->channel_Q];
			pts += dev->num_channels;
			if (si >=  CLIP16 || si <= -CLIP16)
				dev->overrange++;	// assume overrange returns max int
			if (sq >=  CLIP16 || sq <= -CLIP16)
				dev->overrange++;
			ii = si << 16;
			qq = sq << 16;
			cSamples[nSamples++] = ii + I * qq;
			bytes += bytes_per_frame;
			frames--;
			if (bytes == n1)
				pts = (short *)pt2;
		}
		break;
	case 4:
		ptl = (long *)pt1;
		frames = (n1 + n2) / bytes_per_frame;
		bytes = 0;
		while (frames) {
			li = ptl[dev->channel_I];
			lq = ptl[dev->channel_Q];
			ptl += dev->num_channels;
			if (li >=  CLIP32 || li <= -CLIP32)
				dev->overrange++;	// assume overrange returns max int
			if (lq >=  CLIP32 || lq <= -CLIP32)
				dev->overrange++;
			cSamples[nSamples++] = li + I * lq;
			bytes += bytes_per_frame;
			frames--;
			if (bytes == n1)
				ptl = (long *)pt2;
		}
		break;
	case 5:		// use IEEE float
		ptf = (float *)pt1;
		frames = (n1 + n2) / bytes_per_frame;
		bytes = 0;
		while (frames) {
			fi = ptf[dev->channel_I];
			fq = ptf[dev->channel_Q];
			ptf += dev->num_channels;
			if (fabsf(fi) >= 1.0 || fabsf(fq) >= 1.0)
				dev->overrange++;	// assume overrange returns maximum
			cSamples[nSamples++] = (fi + I * fq) * 16777215;
			bytes += bytes_per_frame;
			frames--;
			if (bytes == n1) {
				ptf = (float *)pt2;
			}
		}
		break;
	}
	IDirectSoundCaptureBuffer8_Unlock(ptBuf, pt1, n1, pt2, n2);
	for (i = 0; i < nSamples; i++) {	// DC removal; R.G. Lyons page 553
		c = cSamples[i] + dev->dc_remove * 0.95;
		cSamples[i] = c - dev->dc_remove;
		dev->dc_remove = c;
	}
	return nSamples;
}

void quisk_play_alsa(struct sound_dev * dev, int nSamples,
		complex * cSamples, int report_latency)
{
	LPDIRECTSOUNDBUFFER ptBuf = (LPDIRECTSOUNDBUFFER)dev->buffer;
	DWORD playPos, writePos;	// hardware index into buffer
	static DWORD dataPos=0;		// where to write our data into buffer
	LPVOID pt1, pt2;
	DWORD n1, n2;
	short * pts;
	float * ptf;
	long * ptl;
	int n, count, frames, bytes, pass, bytes_per_frame;
	static int started = 0;

	if ( ! dev->handle || ! dev->buffer)
		return;

	bytes_per_frame = dev->num_channels * dev->sample_bytes;
	bytes = nSamples * bytes_per_frame;
	if (bytes <= 0)
		return;
	if (started) {
		// Note: writePos moves ahead of playPos, not with write activity
		if (IDirectSoundBuffer8_GetCurrentPosition(ptBuf, &playPos, &writePos) != DS_OK) {
#if DEBUG
			printf ("Bad GetCurrentPosition\n");
#endif
			quisk_sound_state.write_error++;
			playPos = writePos = 0;
		}
#if DEBUG > 2
		if (started < 10) {
			started++;
			printf ("Initial playPos %d writePos %d frames %d\n",
				(int)playPos, (int)writePos, (int)(writePos - playPos) / bytes_per_frame);
		}
#endif
		if (report_latency) {			// Report latency for main playback device
			if (dataPos >= playPos)
				count = dataPos - playPos;
			else
				count = dataPos - playPos + dev->play_buf_size;
			frames = count / bytes_per_frame;	// frames in play buffer
			quisk_sound_state.latencyPlay = frames;
		}
		// Measure writePos to dataPos, the space available to write samples
		if (dataPos >= writePos)
			count = dataPos - writePos;
		else
			count = dataPos - writePos + dev->play_buf_size;
		frames = count / bytes_per_frame;	// frames after writePos excluding nSamples
		// Check for underrun as indicated by excessive samples in two-second buffer
		if (frames > dev->sample_rate) {	// more than one second of samples
			quisk_sound_state.underrun_error++;
			// write samples at write pointer + latency
			dataPos = writePos + (dev->latency_frames - nSamples) * bytes_per_frame;
			dataPos = dataPos % dev->play_buf_size;
#if DEBUG
			printf ("Underrun error, frames %d\n", frames);
#endif
		}
		// Check if play buffer is too full
		else if (frames + nSamples > dev->latency_frames * 15 / 10) {
			quisk_sound_state.write_error++;
			// write samples at write pointer + latency
			dataPos = writePos + (dev->latency_frames - nSamples) * bytes_per_frame;
			dataPos = dataPos % dev->play_buf_size;
#if DEBUG
			printf("Discard samples: frames %d exceed %d\n",
				(int)frames, dev->latency_frames);
#endif
		}
	}
	// write our data bytes at our data position dataPos
	if (IDirectSoundBuffer8_Lock(ptBuf, dataPos, bytes, &pt1, &n1, &pt2, &n2, 0) != DS_OK) {
#if DEBUG
		printf ("Lock error\n");
#endif
		quisk_sound_state.write_error++;
		return;
	}
	dataPos += bytes;	// update data write position
	dataPos = dataPos % dev->play_buf_size;
	pass = 0;
	n = 0;
	switch (dev->sample_bytes + dev->use_float) {
	case 2:
		pts = (short *)pt1;	// Start writing at pt1
		frames = n1 / bytes_per_frame;
		for (n = 0; n < nSamples && pass < 2; n++) {
			pts[dev->channel_I] = (short)(creal(cSamples[n]) / 65536);
			pts[dev->channel_Q] = (short)(cimag(cSamples[n]) / 65536);
			pts += dev->num_channels;
			if (--frames <= 0) {
				pass++;
				// change to pt2
				pts = (short *)pt2;
				frames = n2 / bytes_per_frame;
			}
		}
		break;
	case 4:
		ptl = (long *)pt1;	// Start writing at pt1
		frames = n1 / bytes_per_frame;
		for (n = 0; n < nSamples && pass < 2; n++) {
			ptl[dev->channel_I] = (long)(creal(cSamples[n]));
			ptl[dev->channel_Q] = (long)(cimag(cSamples[n]));
			ptl += dev->num_channels;
			if (--frames <= 0) {
				pass++;
				// change to pt2
				ptl = (long *)pt2;
				frames = n2 / bytes_per_frame;
			}
		}
		break;
	case 5:		// use IEEE float
		ptf = (float *)pt1;	// Start writing at pt1
		frames = n1 / bytes_per_frame;
		for (n = 0; n < nSamples && pass < 2; n++) {
			ptf[dev->channel_I] = (creal(cSamples[n]) / CLIP32);
			ptf[dev->channel_Q] = (cimag(cSamples[n]) / CLIP32);
			ptf += dev->num_channels;
			if (--frames <= 0) {
				pass++;
				// change to pt2
				ptf = (float *)pt2;
				frames = n2 / bytes_per_frame;
			}
		}
		break;
	}
	IDirectSoundBuffer8_Unlock(ptBuf, pt1, n1, pt2, n2);
#if DEBUG
	if (n < nSamples)
		printf ("Play error: Not all samples were played.\n");
#endif
	if ( ! started) {	// check start threshold
		frames = dataPos / bytes_per_frame; // frames in play buffer
#if DEBUG > 2
		printf ("Start: %d %d\n", frames, dev->latency_frames);
#endif
		if (frames >= dev->latency_frames * 8 / 10) {
			IDirectSoundBuffer8_Play (ptBuf, 0, 0, DSBPLAY_LOOPING);
			started = 1;
		}
	}
}




void quisk_play_portaudio(struct sound_dev * dev, int j, complex * samp, int i)
{
}

void quisk_start_sound_portaudio(struct sound_dev * dev, struct sound_dev * dev2, struct sound_dev * dev3, struct sound_dev * dev4)
{
}

void quisk_close_sound_portaudio(void)
{
}

int  quisk_read_portaudio(struct sound_dev * dev, complex * samp)
{
	return 0;
}

void quisk_mixer_set(char * card_name, int numid, double value, char * err_msg, int err_size)
{
	err_msg[0] = 0;
}
