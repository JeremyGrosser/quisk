// Export required for Windows
#ifdef MS_WINDOWS
#define QUISK_EXPORT	__declspec(dllexport)
#else
#define QUISK_EXPORT
#endif

// Sound parameters
//
#define QUISK_SC_SIZE		128
#define IP_SIZE				32
#define MAX_FILTER_SIZE		10001
#define BIG_VOLUME			2.2e9
#define CLOSED_TEXT			"The sound device is closed."
#define CLIP32				2147483647
#define CLIP16				32767
#define SAMP_BUFFER_SIZE	66000		// size of arrays used to capture samples
#define IMD_TONE_1			1200		// frequency of IMD test tones
#define IMD_TONE_2			1600
#define INTERP_FILTER_TAPS	85			// interpolation filter
double interpFilterCoef[INTERP_FILTER_TAPS];

// Test the audio: 0 == No test; normal operation;
// 1 == Copy real data to the output; 2 == copy imaginary data to the output;
// 3 == Copy transmit audio to the output.
#define TEST_AUDIO	0

struct sound_dev {				// data for sound capture or playback device
	char name[QUISK_SC_SIZE];	// string name of device
	void * handle;				// Handle of open device, or NULL
	void * buffer;				// Handle of buffer for device
	int portaudio_index;		// index of portaudio device, or -1
	int doAmplPhase;			// Amplitude and Phase corrections
	double AmPhAAAA;
	double AmPhCCCC;
	double AmPhDDDD;
	double portaudio_latency;	// Suggested latency for portaudio device
	int sample_rate;			// Sample rate such as 48000, 96000, 192000
	int sample_bytes;			// Size of one channel sample in bytes, either 2 or 3 or 4
	int num_channels;			// number of channels per frame: 1, 2, 3, ...
	int channel_I;				// Index of I and Q channels: 0, 1, ...
	int channel_Q;
	int channel_Delay;			// Delay this channel by one sample; -1 for no delay, else channel_I or _Q
	int overrange;				// Count for ADC overrange (clip) for device
	int read_frames;			// number of frames for read request
	int latency_frames;			// desired latency in audio play samples
	int play_buf_size;			// size of playback buffer in samples
	int use_float;				// DirectX: Use IEEE floating point
	unsigned int rate_min;		// min and max available sample rates
	unsigned int rate_max;
	unsigned int chan_min;		// min and max available number of channels
	unsigned int chan_max;
	complex dc_remove;			// filter to remove DC from samples
	double save_sample;			// Used to delay the I or Q sample
	char msg1[QUISK_SC_SIZE];	// string for information message
} ;

struct sound_conf {
	char dev_capt_name[QUISK_SC_SIZE];
	char dev_play_name[QUISK_SC_SIZE];
	int sample_rate;		// Input sample rate from the ADC
	int playback_rate;		// Output play rate to sound card
	int data_poll_usec;
	int latency_millisecs;
	unsigned int rate_min;
	unsigned int rate_max;
	unsigned int chan_min;
	unsigned int chan_max;
	int read_error;
	int write_error;
	int underrun_error;
	int overrange;		// count of ADC overrange (clip) for non-soundcard device
	int latencyCapt;
	int latencyPlay;
	int interupts;
	char msg1[QUISK_SC_SIZE];
	char err_msg[QUISK_SC_SIZE];
	// These parameters are for the microphone:
    char mic_dev_name[QUISK_SC_SIZE];			// capture device
	char name_of_mic_play[QUISK_SC_SIZE];		// playback device
    char mic_ip[IP_SIZE];
	int mic_sample_rate;				// capture sample rate
	int mic_playback_rate;				// playback sample rate
	int tx_audio_port;
	int mic_read_error;
	int mic_channel_I;		// channel number for microphone: 0, 1, ...
	int mic_channel_Q;
	int mic_interp;			// integer interpolation for mic playback
	double mic_out_volume;
	// These parameters specify decimation prior to main filters
	int int_filter_decim;
	// Decimation and interpolation after filters
	double double_filter_decim;
	int int_filter_interp;
} ;

extern struct sound_conf quisk_sound_state;
extern int mic_max_display;		// display value of maximum microphone signal level
extern int data_width;
extern int quisk_use_rx_udp;	// is a UDP port used for capture (0 or 1)?
extern int rxMode;				// mode CWL, USB, etc.
extern int quisk_tx_tune_freq;	// Transmit tuning frequency as +/- sample_rate / 2
extern PyObject * quisk_pyConfig;		// Configuration module instance
extern long quisk_mainwin_handle;		// Handle of the main window
extern double quisk_mic_preemphasis;	// Mic preemphasis 0.0 to 1.0; or -1.0
extern double quisk_mic_clip;			// Mic clipping; try 3.0 or 4.0
extern int quisk_noise_blanker;			// Noise blanker level, 0 for off

extern PyObject * quisk_set_tx_filters(PyObject * , PyObject *);

extern PyObject * quisk_set_spot_mode(PyObject * , PyObject *);
extern PyObject * quisk_get_tx_filter(PyObject * , PyObject *);

extern PyObject * quisk_set_ampl_phase(PyObject * , PyObject *);
extern PyObject * quisk_capt_channels(PyObject * , PyObject *);
extern PyObject * quisk_play_channels(PyObject * , PyObject *);
extern PyObject * quisk_micplay_channels(PyObject * , PyObject *);
extern PyObject * quisk_sound_devices(PyObject * , PyObject *);

extern long   QuiskGetConfigLong  (const char *, long);
extern double QuiskGetConfigDouble(const char *, double);
extern char * QuiskGetConfigString(const char *, char *);
extern double QuiskTimeSec(void);
extern void   QuiskSleepMicrosec(int);

// These function pointers are the Start/Stop/Read interface for
// the SDR-IQ and any other C-language extension modules that return
// radio data samples.
typedef void (* ty_sample_start)(void);
typedef void (* ty_sample_stop)(void);
typedef int  (* ty_sample_read)(complex *);
extern ty_sample_start pt_sample_start;
extern ty_sample_stop  pt_sample_stop;
extern ty_sample_read  pt_sample_read;

void quisk_open_sound(void);
void quisk_close_sound(void);
int quisk_process_samples(complex *, int);
void quisk_play_samples(double *, int);
void quisk_play_zeros(int);
void quisk_start_sound(void);
int quisk_get_overrange(void);
void quisk_mixer_set(char *, int, double, char *, int);
int quisk_read_sound(void);
int quisk_process_microphone(complex *, int);
void quisk_open_mic(void);
void quisk_close_mic(void);
int quisk_open_key(const char *);
void quisk_close_key(void);
int quisk_is_key_down(void);
void quisk_set_key_down(int);
int quisk_read_rx_udp(complex *);
void quisk_set_tx_mode(void);
void ptimer(int);
int quisk_extern_demod(complex *, int, double);
int quisk_iDecimate(complex *, int, int);
void quisk_set_decimation(void);

int  quisk_read_alsa(struct sound_dev *, complex *);
void quisk_play_alsa(struct sound_dev *, int, complex *, int);
void quisk_start_sound_alsa(struct sound_dev *, struct sound_dev *, struct sound_dev *,struct sound_dev *);
void quisk_close_sound_alsa(struct sound_dev *, struct sound_dev *, struct sound_dev *,struct sound_dev *);

int  quisk_read_portaudio(struct sound_dev *, complex *);
void quisk_play_portaudio(struct sound_dev *, int, complex *, int);
void quisk_start_sound_portaudio(struct sound_dev *, struct sound_dev *, struct sound_dev *,struct sound_dev *);
void quisk_close_sound_portaudio(void);

