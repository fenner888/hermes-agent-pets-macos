#import <Cocoa/Cocoa.h>
#import <ApplicationServices/ApplicationServices.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreMedia/CoreMedia.h>
#import <CoreAudioTypes/CoreAudioTypes.h>
#import <signal.h>
#import <unistd.h>
#import <sys/proc.h>
#import <sys/sysctl.h>
#import <math.h>

static const NSInteger AtlasWidth = 1536;
static const NSInteger AtlasHeight = 1872;
static const NSInteger CellWidth = 192;
static const NSInteger CellHeight = 208;
static NSString * const DefaultStateFile = @"/tmp/hermes-pet-overlay-state";
static NSString * const DefaultModeFile = @"/tmp/hermes-pet-overlay-mode";
static NSString * const DefaultPositionFile = @"/tmp/hermes-pet-overlay-position";
static NSString * const DefaultAwakeFile = @"/tmp/hermes-pet-overlay-awake";
static const int ReturnKeyCode = 36;
static const int KeypadEnterKeyCode = 76;
static const double AudioActiveRMSThreshold = 0.012;
static const double AudioStopSilenceSeconds = 0.55;

typedef struct {
    NSInteger row;
    NSInteger frames;
    NSTimeInterval duration;
} AnimationState;

static AnimationState StateForName(NSString *name) {
    if ([name isEqualToString:@"running-right"]) return (AnimationState){1, 8, 0.10};
    if ([name isEqualToString:@"running-left"]) return (AnimationState){2, 8, 0.10};
    if ([name isEqualToString:@"waving"]) return (AnimationState){3, 4, 0.18};
    if ([name isEqualToString:@"success"]) return (AnimationState){3, 4, 0.18};
    if ([name isEqualToString:@"dancing"]) return (AnimationState){4, 5, 0.10};
    if ([name isEqualToString:@"jumping"]) return (AnimationState){4, 5, 0.13};
    if ([name isEqualToString:@"failed"]) return (AnimationState){5, 8, 0.16};
    if ([name isEqualToString:@"waiting"]) return (AnimationState){6, 6, 0.22};
    if ([name isEqualToString:@"running"]) return (AnimationState){7, 6, 0.11};
    if ([name isEqualToString:@"review"]) return (AnimationState){8, 6, 0.18};
    return (AnimationState){0, 6, 0.16};
}

static NSString *ArgumentValue(NSString *flag) {
    NSArray<NSString *> *arguments = NSProcessInfo.processInfo.arguments;
    NSUInteger index = [arguments indexOfObject:flag];
    if (index == NSNotFound || index + 1 >= arguments.count) return nil;
    return arguments[index + 1];
}

static BOOL HasArgument(NSString *flag) {
    return [NSProcessInfo.processInfo.arguments containsObject:flag];
}

static NSString *FirstExistingPath(NSArray<NSString *> *candidates) {
    NSFileManager *fileManager = NSFileManager.defaultManager;
    for (NSString *candidate in candidates) {
        if (!candidate.length) continue;
        NSString *path = candidate.stringByExpandingTildeInPath;
        if ([fileManager fileExistsAtPath:path]) return path;
    }
    return nil;
}

static NSString *RepoRootRelativeToApp(void) {
    NSString *executableDir = NSBundle.mainBundle.executablePath.stringByDeletingLastPathComponent;
    NSString *contentsDir = executableDir.stringByDeletingLastPathComponent;
    NSString *appDir = contentsDir.stringByDeletingLastPathComponent;
    NSString *buildDir = appDir.stringByDeletingLastPathComponent;
    return buildDir.stringByDeletingLastPathComponent;
}

static NSString *DefaultHermesPetAssetPath(NSString *filename) {
    NSString *resources = NSBundle.mainBundle.resourcePath ?: @"";
    NSString *repoRoot = RepoRootRelativeToApp();
    NSString *home = NSHomeDirectory() ?: @"";
    return FirstExistingPath(@[
        [resources stringByAppendingPathComponent:[@"koda" stringByAppendingPathComponent:filename]],
        [resources stringByAppendingPathComponent:filename],
        [repoRoot stringByAppendingPathComponent:[@"hermes-agent-pets/hermes-pet-agent/assets/koda" stringByAppendingPathComponent:filename]],
        [repoRoot stringByAppendingPathComponent:[@"character-sets/koda" stringByAppendingPathComponent:filename]],
        [home stringByAppendingPathComponent:[@".hermes/pets/koda" stringByAppendingPathComponent:filename]],
    ]);
}

static NSString *DefaultSpritesheetPath(void) {
    NSString *envPath = NSProcessInfo.processInfo.environment[@"HERMES_PET_SPRITESHEET"];
    if (envPath.length) {
        NSString *expanded = envPath.stringByExpandingTildeInPath;
        if ([NSFileManager.defaultManager fileExistsAtPath:expanded]) return expanded;
    }
    return DefaultHermesPetAssetPath(@"spritesheet.webp") ?: @"spritesheet.webp";
}

static BOOL IsKnownState(NSString *name) {
    NSArray<NSString *> *known = @[
        @"idle", @"running-right", @"running-left", @"waving", @"jumping",
        @"failed", @"waiting", @"running", @"review", @"success", @"dancing"
    ];
    return [known containsObject:name];
}

@interface HermesPetView : NSView
@property(nonatomic) CGImageRef atlas;
@property(nonatomic) CGImageRef danceBobStrip;
@property(nonatomic) CGImageRef danceStepStrip;
@property(nonatomic) CGImageRef danceHitStrip;
@property(nonatomic, copy) NSString *stateName;
@property(nonatomic) BOOL ambientMotion;
@property(nonatomic) NSInteger frameIndex;
@property(nonatomic) NSInteger tickCount;
@property(nonatomic) NSInteger danceBobFrameCount;
@property(nonatomic) NSInteger danceStepFrameCount;
@property(nonatomic) NSInteger danceHitFrameCount;
@property(nonatomic) NSInteger danceMoveIndex;
@property(nonatomic) NSInteger danceAccentFramesRemaining;
@property(nonatomic, strong) NSTimer *timer;
- (void)setAnimationState:(NSString *)stateName;
- (void)setDanceBobPath:(NSString *)bobPath stepPath:(NSString *)stepPath hitPath:(NSString *)hitPath;
- (void)advanceDanceFrameWithStrongBeat:(BOOL)strongBeat;
@end

@implementation HermesPetView

- (instancetype)initWithAtlas:(CGImageRef)atlas stateName:(NSString *)stateName ambientMotion:(BOOL)ambientMotion {
    self = [super initWithFrame:NSZeroRect];
    if (!self) return nil;

    _atlas = CGImageRetain(atlas);
    _stateName = [stateName copy] ?: @"idle";
    _ambientMotion = ambientMotion;
    _frameIndex = 0;
    _tickCount = 0;
    self.wantsLayer = YES;
    self.layer.backgroundColor = NSColor.clearColor.CGColor;

    [self resetTimer];
    return self;
}

- (void)dealloc {
    [_timer invalidate];
    if (_atlas) CGImageRelease(_atlas);
    if (_danceBobStrip) CGImageRelease(_danceBobStrip);
    if (_danceStepStrip) CGImageRelease(_danceStepStrip);
    if (_danceHitStrip) CGImageRelease(_danceHitStrip);
}

- (CGImageRef)loadImageAtPath:(NSString *)path {
    if (!path.length) return nil;
    NSString *expandedPath = path.stringByExpandingTildeInPath;
    NSImage *image = [[NSImage alloc] initWithContentsOfFile:expandedPath];
    if (!image) return nil;
    NSRect rect = NSMakeRect(0, 0, image.size.width, image.size.height);
    CGImageRef cgImage = [image CGImageForProposedRect:&rect context:nil hints:nil];
    return cgImage ? CGImageRetain(cgImage) : nil;
}

- (NSInteger)frameCountForStrip:(CGImageRef)strip {
    if (!strip) return 0;
    CGFloat imageWidth = (CGFloat)CGImageGetWidth(strip);
    CGFloat imageHeight = (CGFloat)CGImageGetHeight(strip);
    if (imageWidth <= 0.0 || imageHeight <= 0.0) return 0;
    CGFloat cellAspect = (CGFloat)CellWidth / (CGFloat)CellHeight;
    return MAX(1, MIN(12, (NSInteger)lround(imageWidth / (imageHeight * cellAspect))));
}

- (void)setDanceBobPath:(NSString *)bobPath stepPath:(NSString *)stepPath hitPath:(NSString *)hitPath {
    if (_danceBobStrip) CGImageRelease(_danceBobStrip);
    if (_danceStepStrip) CGImageRelease(_danceStepStrip);
    if (_danceHitStrip) CGImageRelease(_danceHitStrip);
    _danceBobStrip = [self loadImageAtPath:bobPath];
    _danceStepStrip = [self loadImageAtPath:stepPath];
    _danceHitStrip = [self loadImageAtPath:hitPath];
    _danceBobFrameCount = [self frameCountForStrip:_danceBobStrip];
    _danceStepFrameCount = [self frameCountForStrip:_danceStepStrip];
    _danceHitFrameCount = [self frameCountForStrip:_danceHitStrip];
}

- (void)setAnimationState:(NSString *)stateName {
    if (!IsKnownState(stateName)) return;
    self.stateName = stateName;
    self.frameIndex = 0;
    self.tickCount = 0;
    [self resetTimer];
    self.needsDisplay = YES;
}

- (void)resetTimer {
    [self.timer invalidate];
    self.timer = nil;
    if ([self.stateName isEqualToString:@"idle"] && !self.ambientMotion) return;
    if ([self.stateName isEqualToString:@"dancing"] && (self.danceBobStrip || self.danceStepStrip || self.danceHitStrip)) return;

    AnimationState state = StateForName(self.stateName);
    self.timer = [NSTimer scheduledTimerWithTimeInterval:state.duration
                                                  target:self
                                                selector:@selector(advanceFrame)
                                                userInfo:nil
                                                 repeats:YES];
}

- (void)advanceFrame {
    AnimationState state = StateForName(self.stateName);
    self.frameIndex = (self.frameIndex + 1) % state.frames;
    self.tickCount += 1;

    if ([self.stateName isEqualToString:@"idle"] && self.tickCount > 180) {
        [self setAnimationState:@"waving"];
    } else if ([self.stateName isEqualToString:@"waving"] && self.frameIndex == state.frames - 1) {
        [self setAnimationState:@"idle"];
    } else if ([self.stateName isEqualToString:@"success"] && self.frameIndex == state.frames - 1) {
        [self setAnimationState:@"idle"];
    }

    self.needsDisplay = YES;
}

- (void)advanceDanceFrameWithStrongBeat:(BOOL)strongBeat {
    if (![self.stateName isEqualToString:@"dancing"]) return;
    if (!(self.danceBobStrip || self.danceStepStrip || self.danceHitStrip)) return;
    self.danceMoveIndex += 1;
    self.frameIndex += 1;
    if (strongBeat && self.danceHitStrip) {
        self.danceAccentFramesRemaining = 1;
        self.frameIndex = (self.frameIndex + 1) % MAX(1, self.danceHitFrameCount);
    }
    self.needsDisplay = YES;
}

- (BOOL)drawDanceStripInContext:(CGContextRef)context {
    if (![self.stateName isEqualToString:@"dancing"]) return NO;
    CGImageRef strip = nil;
    NSInteger frameCount = 0;
    if (self.danceAccentFramesRemaining > 0 && self.danceHitStrip) {
        strip = self.danceHitStrip;
        frameCount = self.danceHitFrameCount;
        self.danceAccentFramesRemaining -= 1;
    } else if (((self.danceMoveIndex / 8) % 2) == 0 && self.danceBobStrip) {
        strip = self.danceBobStrip;
        frameCount = self.danceBobFrameCount;
    } else if (self.danceStepStrip) {
        strip = self.danceStepStrip;
        frameCount = self.danceStepFrameCount;
    } else {
        strip = self.danceBobStrip ?: self.danceHitStrip;
        frameCount = strip == self.danceBobStrip ? self.danceBobFrameCount : self.danceHitFrameCount;
    }
    if (!strip || frameCount < 1) return NO;

    size_t imageWidth = CGImageGetWidth(strip);
    size_t imageHeight = CGImageGetHeight(strip);
    size_t frameWidth = MAX(1, imageWidth / (size_t)frameCount);
    size_t frameIndex = (size_t)(self.frameIndex % frameCount);
    CGRect source = CGRectMake(frameWidth * frameIndex, 0, frameWidth, imageHeight);
    CGImageRef frame = CGImageCreateWithImageInRect(strip, source);
    if (!frame) return YES;
    CGContextDrawImage(context, NSRectToCGRect(self.bounds), frame);
    CGImageRelease(frame);
    return YES;
}

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];
    if (!self.atlas) return;
    CGContextRef context = NSGraphicsContext.currentContext.CGContext;
    CGContextSetInterpolationQuality(context, kCGInterpolationNone);
    if ([self drawDanceStripInContext:context]) return;

    AnimationState state = StateForName(self.stateName);
    CGRect source = CGRectMake(
        self.frameIndex * CellWidth,
        state.row * CellHeight,
        CellWidth,
        CellHeight
    );

    CGImageRef frame = CGImageCreateWithImageInRect(self.atlas, source);
    if (!frame) return;

    CGContextDrawImage(context, NSRectToCGRect(self.bounds), frame);
    CGImageRelease(frame);
}

@end

@interface AudioReactiveMonitor : NSObject <SCStreamOutput, SCStreamDelegate>
@property(nonatomic, strong) SCStream *stream;
@property(nonatomic) dispatch_queue_t queue;
@property(nonatomic, copy) void (^levelHandler)(double rms, BOOL beat);
@property(nonatomic) double smoothedRMS;
@property(nonatomic) NSTimeInterval lastBeatAt;
- (instancetype)initWithLevelHandler:(void (^)(double rms, BOOL beat))levelHandler;
- (void)start;
- (void)stop;
@end

@implementation AudioReactiveMonitor

- (instancetype)initWithLevelHandler:(void (^)(double rms, BOOL beat))levelHandler {
    self = [super init];
    if (!self) return nil;
    _levelHandler = [levelHandler copy];
    _queue = dispatch_queue_create("local.hermes.pet.overlay.audio-reactive", DISPATCH_QUEUE_SERIAL);
    _smoothedRMS = 0.0;
    _lastBeatAt = 0.0;
    return self;
}

- (void)start {
    if (self.stream) return;
    if (@available(macOS 13.0, *)) {
        [SCShareableContent getShareableContentExcludingDesktopWindows:YES
                                                   onScreenWindowsOnly:YES
                                                     completionHandler:^(SCShareableContent * _Nullable content, NSError * _Nullable error) {
            if (error || content.displays.count == 0) {
                NSLog(@"Hermes pet audio-reactive capture unavailable: %@", error.localizedDescription ?: @"no display");
                return;
            }

            SCDisplay *display = content.displays.firstObject;
            SCContentFilter *filter = [[SCContentFilter alloc] initWithDisplay:display excludingWindows:@[]];
            SCStreamConfiguration *config = [[SCStreamConfiguration alloc] init];
            config.width = 2;
            config.height = 2;
            config.minimumFrameInterval = CMTimeMake(1, 2);
            config.queueDepth = 1;
            config.showsCursor = NO;
            config.capturesAudio = YES;
            config.excludesCurrentProcessAudio = YES;
            config.sampleRate = 44100;
            config.channelCount = 2;

            SCStream *stream = [[SCStream alloc] initWithFilter:filter configuration:config delegate:self];
            NSError *outputError = nil;
            if (![stream addStreamOutput:self type:SCStreamOutputTypeAudio sampleHandlerQueue:self.queue error:&outputError]) {
                NSLog(@"Hermes pet audio-reactive output failed: %@", outputError.localizedDescription);
                return;
            }
            self.stream = stream;
            [stream startCaptureWithCompletionHandler:^(NSError * _Nullable startError) {
                if (startError) {
                    NSLog(@"Hermes pet audio-reactive capture failed: %@", startError.localizedDescription);
                    self.stream = nil;
                }
            }];
        }];
    }
}

- (void)stop {
    SCStream *stream = self.stream;
    self.stream = nil;
    if (stream) {
        [stream stopCaptureWithCompletionHandler:nil];
    }
}

- (double)rmsForSampleBuffer:(CMSampleBufferRef)sampleBuffer {
    CMFormatDescriptionRef formatDescription = CMSampleBufferGetFormatDescription(sampleBuffer);
    const AudioStreamBasicDescription *format = CMAudioFormatDescriptionGetStreamBasicDescription(formatDescription);
    if (!format) return 0.0;

    size_t needed = 0;
    CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(sampleBuffer,
                                                            &needed,
                                                            NULL,
                                                            0,
                                                            NULL,
                                                            NULL,
                                                            0,
                                                            NULL);
    if (needed == 0) return 0.0;

    AudioBufferList *bufferList = (AudioBufferList *)calloc(1, needed);
    if (!bufferList) return 0.0;

    CMBlockBufferRef blockBuffer = NULL;
    OSStatus status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(sampleBuffer,
                                                                              NULL,
                                                                              bufferList,
                                                                              needed,
                                                                              NULL,
                                                                              NULL,
                                                                              kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
                                                                              &blockBuffer);
    if (status != noErr) {
        free(bufferList);
        if (blockBuffer) CFRelease(blockBuffer);
        return 0.0;
    }

    BOOL isFloat = (format->mFormatFlags & kAudioFormatFlagIsFloat) != 0;
    BOOL isSignedInteger = (format->mFormatFlags & kAudioFormatFlagIsSignedInteger) != 0;
    UInt32 bytesPerSample = MAX(1, format->mBitsPerChannel / 8);
    double sum = 0.0;
    NSUInteger sampleCount = 0;

    for (UInt32 bufferIndex = 0; bufferIndex < bufferList->mNumberBuffers; bufferIndex++) {
        AudioBuffer audioBuffer = bufferList->mBuffers[bufferIndex];
        if (!audioBuffer.mData || audioBuffer.mDataByteSize == 0) continue;
        NSUInteger count = audioBuffer.mDataByteSize / bytesPerSample;
        if (isFloat && bytesPerSample == 4) {
            float *samples = (float *)audioBuffer.mData;
            for (NSUInteger i = 0; i < count; i++) {
                double value = samples[i];
                sum += value * value;
            }
            sampleCount += count;
        } else if (isSignedInteger && bytesPerSample == 2) {
            int16_t *samples = (int16_t *)audioBuffer.mData;
            for (NSUInteger i = 0; i < count; i++) {
                double value = (double)samples[i] / 32768.0;
                sum += value * value;
            }
            sampleCount += count;
        } else if (isSignedInteger && bytesPerSample == 4) {
            int32_t *samples = (int32_t *)audioBuffer.mData;
            for (NSUInteger i = 0; i < count; i++) {
                double value = (double)samples[i] / 2147483648.0;
                sum += value * value;
            }
            sampleCount += count;
        }
    }

    free(bufferList);
    if (blockBuffer) CFRelease(blockBuffer);
    if (sampleCount == 0) return 0.0;
    return sqrt(sum / (double)sampleCount);
}

- (void)stream:(SCStream *)stream didOutputSampleBuffer:(CMSampleBufferRef)sampleBuffer ofType:(SCStreamOutputType)type {
    if (@available(macOS 13.0, *)) {
        if (type != SCStreamOutputTypeAudio) return;
    }
    if (!CMSampleBufferIsValid(sampleBuffer) || !CMSampleBufferDataIsReady(sampleBuffer)) return;

    double rms = [self rmsForSampleBuffer:sampleBuffer];
    self.smoothedRMS = self.smoothedRMS * 0.92 + rms * 0.08;
    NSTimeInterval now = NSDate.date.timeIntervalSince1970;
    BOOL beat = rms > MAX(0.035, self.smoothedRMS * 1.55) && (now - self.lastBeatAt) > 0.22;
    if (beat) self.lastBeatAt = now;

    if (self.levelHandler) {
        dispatch_async(dispatch_get_main_queue(), ^{
            self.levelHandler(rms, beat);
        });
    }
}

- (void)stream:(SCStream *)stream didStopWithError:(NSError *)error {
    NSLog(@"Hermes pet audio-reactive capture stopped: %@", error.localizedDescription);
    self.stream = nil;
}

@end

@interface StopHeroView : NSView
@property(nonatomic) CGImageRef atlas;
@property(nonatomic) CGImageRef stopPose;
@property(nonatomic) CGImageRef runPose;
@property(nonatomic) NSInteger stopPoseFrameIndex;
@property(nonatomic) NSInteger stopPoseFrameCount;
@property(nonatomic) NSInteger runPoseFrameCount;
@property(nonatomic) BOOL frozenAtMaxSize;
@property(nonatomic, strong) NSTimer *stopPoseFrameTimer;
- (instancetype)initWithAtlas:(CGImageRef)atlas stopPosePath:(NSString *)stopPosePath runPosePath:(NSString *)runPosePath;
- (void)freezeStopPoseAtMaxSize;
@end

@implementation StopHeroView

- (CGImageRef)loadImageAtPath:(NSString *)path {
    if (!path.length) return nil;
    NSString *expandedPath = path.stringByExpandingTildeInPath;
    NSImage *image = [[NSImage alloc] initWithContentsOfFile:expandedPath];
    if (!image) return nil;
    NSRect rect = NSMakeRect(0, 0, image.size.width, image.size.height);
    CGImageRef cgImage = [image CGImageForProposedRect:&rect context:nil hints:nil];
    return cgImage ? CGImageRetain(cgImage) : nil;
}

- (NSInteger)frameCountForImage:(CGImageRef)image {
    if (!image) return 1;
    CGFloat imageWidth = (CGFloat)CGImageGetWidth(image);
    CGFloat imageHeight = (CGFloat)CGImageGetHeight(image);
    if (imageWidth <= imageHeight * 1.6) return 1;
    return MIN(12, MAX(1, (NSInteger)lround(imageWidth / imageHeight * 2.0)));
}

- (instancetype)initWithAtlas:(CGImageRef)atlas stopPosePath:(NSString *)stopPosePath runPosePath:(NSString *)runPosePath {
    self = [super initWithFrame:NSZeroRect];
    if (!self) return nil;
    _atlas = CGImageRetain(atlas);
    _stopPose = [self loadImageAtPath:stopPosePath];
    _runPose = [self loadImageAtPath:runPosePath];
    _stopPoseFrameCount = [self frameCountForImage:_stopPose];
    _runPoseFrameCount = [self frameCountForImage:_runPose];
    NSInteger animatedFrameCount = _runPose ? _runPoseFrameCount : _stopPoseFrameCount;
    if (animatedFrameCount > 1) {
        _stopPoseFrameTimer = [NSTimer scheduledTimerWithTimeInterval:0.11
                                                                target:self
                                                              selector:@selector(advanceStopPoseFrame)
                                                              userInfo:nil
                                                               repeats:YES];
    }
    if (_stopPoseFrameCount < 1) _stopPoseFrameCount = 1;
    if (_runPoseFrameCount < 1) _runPoseFrameCount = 1;
    self.wantsLayer = YES;
    self.layer.backgroundColor = NSColor.clearColor.CGColor;
    return self;
}

- (void)dealloc {
    [_stopPoseFrameTimer invalidate];
    if (_atlas) CGImageRelease(_atlas);
    if (_stopPose) CGImageRelease(_stopPose);
    if (_runPose) CGImageRelease(_runPose);
}

- (void)advanceStopPoseFrame {
    NSInteger frameCount = self.frozenAtMaxSize ? self.stopPoseFrameCount : (self.runPose ? self.runPoseFrameCount : self.stopPoseFrameCount);
    self.stopPoseFrameIndex = (self.stopPoseFrameIndex + 1) % MAX(1, frameCount);
    self.needsDisplay = YES;
}

- (void)freezeStopPoseAtMaxSize {
    [self.stopPoseFrameTimer invalidate];
    self.stopPoseFrameTimer = nil;
    self.frozenAtMaxSize = YES;
    self.stopPoseFrameIndex = MAX(0, self.stopPoseFrameCount - 1);
    self.needsDisplay = YES;
}

- (CGRect)aspectFitRectForImageWidth:(CGFloat)imageWidth height:(CGFloat)imageHeight inBounds:(NSRect)bounds {
    if (imageWidth <= 0.0 || imageHeight <= 0.0) return NSRectToCGRect(bounds);
    CGFloat scale = MIN(bounds.size.width / imageWidth, bounds.size.height / imageHeight);
    CGFloat width = imageWidth * scale;
    CGFloat height = imageHeight * scale;
    return CGRectMake(NSMidX(bounds) - width / 2.0,
                      NSMidY(bounds) - height / 2.0,
                      width,
                      height);
}

- (void)drawStopSignInRect:(NSRect)signRect {
    CGContextRef context = NSGraphicsContext.currentContext.CGContext;
    NSBezierPath *pole = [NSBezierPath bezierPathWithRoundedRect:NSMakeRect(NSMidX(signRect) - signRect.size.width * 0.035,
                                                                             NSMinY(signRect) - signRect.size.height * 0.56,
                                                                             signRect.size.width * 0.07,
                                                                             signRect.size.height * 0.72)
                                                         xRadius:signRect.size.width * 0.025
                                                         yRadius:signRect.size.width * 0.025];
    [[NSColor colorWithCalibratedWhite:0.72 alpha:1.0] setFill];
    [pole fill];
    [[NSColor colorWithCalibratedWhite:0.18 alpha:1.0] setStroke];
    pole.lineWidth = MAX(2.0, signRect.size.width * 0.016);
    [pole stroke];

    NSBezierPath *octagon = [NSBezierPath bezierPath];
    CGFloat inset = signRect.size.width * 0.30;
    NSPoint points[] = {
        NSMakePoint(NSMinX(signRect) + inset, NSMaxY(signRect)),
        NSMakePoint(NSMaxX(signRect) - inset, NSMaxY(signRect)),
        NSMakePoint(NSMaxX(signRect), NSMaxY(signRect) - inset),
        NSMakePoint(NSMaxX(signRect), NSMinY(signRect) + inset),
        NSMakePoint(NSMaxX(signRect) - inset, NSMinY(signRect)),
        NSMakePoint(NSMinX(signRect) + inset, NSMinY(signRect)),
        NSMakePoint(NSMinX(signRect), NSMinY(signRect) + inset),
        NSMakePoint(NSMinX(signRect), NSMaxY(signRect) - inset)
    };
    [octagon moveToPoint:points[0]];
    for (NSUInteger index = 1; index < 8; index++) [octagon lineToPoint:points[index]];
    [octagon closePath];

    [NSGraphicsContext saveGraphicsState];
    NSShadow *shadow = [[NSShadow alloc] init];
    shadow.shadowBlurRadius = MAX(8.0, signRect.size.width * 0.08);
    shadow.shadowOffset = NSMakeSize(0, -signRect.size.width * 0.02);
    shadow.shadowColor = [NSColor colorWithWhite:0 alpha:0.32];
    [shadow set];
    [[NSColor colorWithCalibratedRed:0.88 green:0.04 blue:0.03 alpha:1.0] setFill];
    [octagon fill];
    [NSGraphicsContext restoreGraphicsState];

    NSBezierPath *inner = [octagon copy];
    [NSColor.whiteColor setStroke];
    inner.lineWidth = MAX(5.0, signRect.size.width * 0.06);
    [inner stroke];
    [[NSColor colorWithCalibratedWhite:0.08 alpha:1.0] setStroke];
    octagon.lineWidth = MAX(2.0, signRect.size.width * 0.016);
    [octagon stroke];

    NSMutableParagraphStyle *style = [[NSMutableParagraphStyle alloc] init];
    style.alignment = NSTextAlignmentCenter;
    NSDictionary *attributes = @{
        NSFontAttributeName: [NSFont boldSystemFontOfSize:MAX(18.0, signRect.size.width * 0.25)],
        NSForegroundColorAttributeName: NSColor.whiteColor,
        NSParagraphStyleAttributeName: style
    };
    [@"STOP" drawInRect:NSInsetRect(signRect, signRect.size.width * 0.10, signRect.size.height * 0.35)
         withAttributes:attributes];
    CGContextSetInterpolationQuality(context, kCGInterpolationNone);
}

- (void)drawAtlasFallbackStopHeroInContext:(CGContextRef)context {
    if (!self.atlas) return;

    NSInteger row = self.frozenAtMaxSize ? 0 : 1;
    NSInteger frameCount = self.frozenAtMaxSize ? 6 : 8;
    NSInteger frameIndex = self.frozenAtMaxSize ? 0 : (self.stopPoseFrameIndex % MAX(1, frameCount));
    CGRect source = CGRectMake(CellWidth * frameIndex, CellHeight * row, CellWidth, CellHeight);
    CGImageRef pet = CGImageCreateWithImageInRect(self.atlas, source);
    if (pet) {
        CGFloat petHeight = self.bounds.size.height * (self.frozenAtMaxSize ? 0.58 : 0.46);
        CGFloat petWidth = petHeight * (CellWidth / CellHeight);
        CGFloat petX = self.bounds.size.width * (self.frozenAtMaxSize ? 0.16 : 0.25);
        CGFloat petY = self.bounds.size.height * (self.frozenAtMaxSize ? 0.07 : 0.13);
        if (!self.frozenAtMaxSize) {
            CGFloat bob = sin((double)self.stopPoseFrameIndex * 0.95) * self.bounds.size.height * 0.012;
            petY += bob;
        }
        CGRect destination = CGRectMake(petX, petY, petWidth, petHeight);
        CGContextDrawImage(context, destination, pet);
        CGImageRelease(pet);
    }

    CGFloat signSize = MIN(self.bounds.size.width, self.bounds.size.height) * (self.frozenAtMaxSize ? 0.34 : 0.28);
    CGFloat signX = self.bounds.size.width * (self.frozenAtMaxSize ? 0.58 : 0.56);
    CGFloat signY = self.bounds.size.height * (self.frozenAtMaxSize ? 0.48 : 0.43);
    [self drawStopSignInRect:NSMakeRect(signX, signY, signSize, signSize)];
}

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];
    CGContextRef context = NSGraphicsContext.currentContext.CGContext;
    CGContextSetInterpolationQuality(context, kCGInterpolationNone);
    CGImageRef activePose = (!self.frozenAtMaxSize && self.runPose) ? self.runPose : self.stopPose;
    NSInteger activeFrameCount = (!self.frozenAtMaxSize && self.runPose) ? self.runPoseFrameCount : self.stopPoseFrameCount;
    if (activePose) {
        size_t imageWidth = CGImageGetWidth(activePose);
        size_t imageHeight = CGImageGetHeight(activePose);
        size_t frameCount = MAX(1, (size_t)activeFrameCount);
        size_t frameWidth = MAX(1, imageWidth / frameCount);
        size_t frameIndex = (size_t)(self.stopPoseFrameIndex % (NSInteger)frameCount);
        size_t sourceHeight = imageHeight;
        if (self.frozenAtMaxSize && activePose == self.stopPose && self.runPose) {
            sourceHeight = MAX(1, (size_t)floor((CGFloat)imageHeight * 0.72));
        }
        CGRect source = CGRectMake(frameWidth * frameIndex, 0, frameWidth, sourceHeight);
        CGImageRef frame = CGImageCreateWithImageInRect(activePose, source);
        if (frame) {
            CGRect destination = [self aspectFitRectForImageWidth:(CGFloat)frameWidth
                                                           height:(CGFloat)sourceHeight
                                                         inBounds:self.bounds];
            CGContextDrawImage(context, destination, frame);
            CGImageRelease(frame);
        }
        return;
    }
    [self drawAtlasFallbackStopHeroInContext:context];
}

@end

@interface BubbleView : NSView
@property(nonatomic, copy) NSString *text;
- (instancetype)initWithText:(NSString *)text;
@end

@implementation BubbleView

- (instancetype)initWithText:(NSString *)text {
    self = [super initWithFrame:NSZeroRect];
    if (!self) return nil;
    _text = [text copy] ?: @"";
    self.wantsLayer = YES;
    self.layer.backgroundColor = NSColor.clearColor.CGColor;
    return self;
}

- (void)setText:(NSString *)text {
    _text = [text copy] ?: @"";
    self.needsDisplay = YES;
}

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];
    NSRect bubbleRect = NSInsetRect(self.bounds, 2.0, 2.0);
    CGFloat radius = 10.0;
    NSBezierPath *bubble = [NSBezierPath bezierPathWithRoundedRect:bubbleRect
                                                           xRadius:radius
                                                           yRadius:radius];

    [NSGraphicsContext saveGraphicsState];
    NSShadow *shadow = [[NSShadow alloc] init];
    shadow.shadowBlurRadius = 10.0;
    shadow.shadowOffset = NSMakeSize(0, -2);
    shadow.shadowColor = [NSColor colorWithWhite:0 alpha:0.24];
    [shadow set];
    [[NSColor colorWithCalibratedWhite:0.08 alpha:0.86] setFill];
    [bubble fill];
    [NSGraphicsContext restoreGraphicsState];

    [[NSColor colorWithCalibratedWhite:1.0 alpha:0.22] setStroke];
    bubble.lineWidth = 1.0;
    [bubble stroke];

    NSMutableParagraphStyle *style = [[NSMutableParagraphStyle alloc] init];
    style.alignment = NSTextAlignmentCenter;
    NSDictionary *attributes = @{
        NSFontAttributeName: [NSFont systemFontOfSize:13.0 weight:NSFontWeightSemibold],
        NSForegroundColorAttributeName: NSColor.whiteColor,
        NSParagraphStyleAttributeName: style
    };
    NSRect textRect = NSInsetRect(bubbleRect, 12.0, 6.0);
    [self.text drawInRect:textRect withAttributes:attributes];
}

@end

@interface StopSignView : NSView
@end

@implementation StopSignView

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];
    NSRect rect = self.bounds;
    CGFloat size = MIN(rect.size.width, rect.size.height) * 0.92;
    NSRect signRect = NSMakeRect(NSMidX(rect) - size / 2.0,
                                 NSMidY(rect) - size / 2.0,
                                 size,
                                 size);

    NSBezierPath *octagon = [NSBezierPath bezierPath];
    CGFloat inset = size * 0.30;
    NSPoint points[] = {
        NSMakePoint(NSMinX(signRect) + inset, NSMaxY(signRect)),
        NSMakePoint(NSMaxX(signRect) - inset, NSMaxY(signRect)),
        NSMakePoint(NSMaxX(signRect), NSMaxY(signRect) - inset),
        NSMakePoint(NSMaxX(signRect), NSMinY(signRect) + inset),
        NSMakePoint(NSMaxX(signRect) - inset, NSMinY(signRect)),
        NSMakePoint(NSMinX(signRect) + inset, NSMinY(signRect)),
        NSMakePoint(NSMinX(signRect), NSMinY(signRect) + inset),
        NSMakePoint(NSMinX(signRect), NSMaxY(signRect) - inset)
    };

    [octagon moveToPoint:points[0]];
    for (NSUInteger index = 1; index < 8; index++) {
        [octagon lineToPoint:points[index]];
    }
    [octagon closePath];

    [NSGraphicsContext saveGraphicsState];
    NSShadow *shadow = [[NSShadow alloc] init];
    shadow.shadowBlurRadius = 18;
    shadow.shadowOffset = NSMakeSize(0, -5);
    shadow.shadowColor = [NSColor colorWithWhite:0 alpha:0.35];
    [shadow set];
    [[NSColor colorWithCalibratedRed:0.86 green:0.05 blue:0.04 alpha:1.0] setFill];
    [octagon fill];
    [NSGraphicsContext restoreGraphicsState];

    [NSColor.whiteColor setStroke];
    octagon.lineWidth = MAX(6, size * 0.065);
    [octagon stroke];

    NSMutableParagraphStyle *style = [[NSMutableParagraphStyle alloc] init];
    style.alignment = NSTextAlignmentCenter;
    NSDictionary *attributes = @{
        NSFontAttributeName: [NSFont boldSystemFontOfSize:size * 0.28],
        NSForegroundColorAttributeName: NSColor.whiteColor,
        NSParagraphStyleAttributeName: style
    };
    NSRect textRect = NSInsetRect(signRect, size * 0.08, size * 0.34);
    [@"STOP" drawInRect:textRect withAttributes:attributes];
}

@end

@interface GuardPoseView : NSView
@property(nonatomic) CGImageRef pose;
@property(nonatomic) CGRect visibleImageRect;
@property(nonatomic) BOOL hasVisibleImageRect;
- (instancetype)initWithPosePath:(NSString *)posePath;
@end

@implementation GuardPoseView

- (instancetype)initWithPosePath:(NSString *)posePath {
    self = [super initWithFrame:NSZeroRect];
    if (!self) return nil;
    if (posePath.length) {
        NSString *expandedPath = posePath.stringByExpandingTildeInPath;
        NSImage *image = [[NSImage alloc] initWithContentsOfFile:expandedPath];
        if (image) {
            NSRect rect = NSMakeRect(0, 0, image.size.width, image.size.height);
            CGImageRef cgImage = [image CGImageForProposedRect:&rect context:nil hints:nil];
            if (cgImage) _pose = CGImageRetain(cgImage);
        }
    }
    self.wantsLayer = YES;
    self.layer.backgroundColor = NSColor.clearColor.CGColor;
    return self;
}

- (void)dealloc {
    if (_pose) CGImageRelease(_pose);
}

- (CGRect)bottomAlignedAspectFitRectForImageWidth:(CGFloat)imageWidth height:(CGFloat)imageHeight inBounds:(NSRect)bounds {
    if (imageWidth <= 0.0 || imageHeight <= 0.0) return NSRectToCGRect(bounds);
    CGFloat scale = MIN(bounds.size.width / imageWidth, bounds.size.height / imageHeight);
    CGFloat width = imageWidth * scale;
    CGFloat height = imageHeight * scale;
    return CGRectMake(NSMidX(bounds) - width / 2.0,
                      NSMinY(bounds),
                      width,
                      height);
}

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];
    if (!self.pose) return;
    size_t width = CGImageGetWidth(self.pose);
    size_t height = CGImageGetHeight(self.pose);
    CGRect sourceRect = self.hasVisibleImageRect ? self.visibleImageRect : CGRectMake(0, 0, width, height);
    sourceRect = CGRectIntersection(sourceRect, CGRectMake(0, 0, width, height));
    if (CGRectIsEmpty(sourceRect)) return;
    CGImageRef cropped = CGImageCreateWithImageInRect(self.pose, sourceRect);
    if (!cropped) return;
    CGContextRef context = NSGraphicsContext.currentContext.CGContext;
    CGContextSetInterpolationQuality(context, kCGInterpolationNone);
    CGRect fullDestination = [self bottomAlignedAspectFitRectForImageWidth:(CGFloat)width
                                                                    height:(CGFloat)height
                                                                  inBounds:self.bounds];
    CGRect destination = fullDestination;
    if (self.hasVisibleImageRect) {
        CGFloat scaleX = fullDestination.size.width / (CGFloat)width;
        CGFloat scaleY = fullDestination.size.height / (CGFloat)height;
        destination = CGRectMake(fullDestination.origin.x + sourceRect.origin.x * scaleX,
                                 fullDestination.origin.y + ((CGFloat)height - CGRectGetMaxY(sourceRect)) * scaleY,
                                 sourceRect.size.width * scaleX,
                                 sourceRect.size.height * scaleY);
    }
    CGContextDrawImage(context, destination, cropped);
    CGImageRelease(cropped);
}

@end

@interface GuardPanelView : NSView
@end

@implementation GuardPanelView

- (instancetype)initWithFrame:(NSRect)frame {
    self = [super initWithFrame:frame];
    if (!self) return nil;
    self.wantsLayer = YES;
    self.layer.backgroundColor = NSColor.clearColor.CGColor;
    return self;
}

- (void)drawCornerCircuitInRect:(NSRect)rect topLeft:(BOOL)topLeft {
    CGFloat x = topLeft ? NSMinX(rect) : NSMaxX(rect);
    CGFloat y = topLeft ? NSMaxY(rect) : NSMinY(rect);
    NSBezierPath *line = [NSBezierPath bezierPath];
    if (topLeft) {
        [line moveToPoint:NSMakePoint(x + 18, y - 38)];
        [line lineToPoint:NSMakePoint(x + 18, y - 18)];
        [line lineToPoint:NSMakePoint(x + 38, y - 18)];
        [line moveToPoint:NSMakePoint(x + 54, y - 18)];
        [line lineToPoint:NSMakePoint(x + 92, y - 18)];
    } else {
        [line moveToPoint:NSMakePoint(x - 18, y + 38)];
        [line lineToPoint:NSMakePoint(x - 18, y + 18)];
        [line lineToPoint:NSMakePoint(x - 38, y + 18)];
        [line moveToPoint:NSMakePoint(x - 54, y + 18)];
        [line lineToPoint:NSMakePoint(x - 92, y + 18)];
    }
    line.lineWidth = 1.3;
    [[NSColor colorWithCalibratedRed:1.0 green:0.47 blue:0.04 alpha:0.58] setStroke];
    [line stroke];
}

- (void)drawProtocolBadgeAtPoint:(NSPoint)point {
    NSBezierPath *hex = [NSBezierPath bezierPath];
    CGFloat radius = 13.0;
    for (NSInteger i = 0; i < 6; i++) {
        CGFloat angle = M_PI / 6.0 + (M_PI * 2.0 * i / 6.0);
        NSPoint p = NSMakePoint(point.x + cos(angle) * radius, point.y + sin(angle) * radius);
        i == 0 ? [hex moveToPoint:p] : [hex lineToPoint:p];
    }
    [hex closePath];
    hex.lineWidth = 1.6;
    [[NSColor colorWithCalibratedRed:1.0 green:0.48 blue:0.08 alpha:0.9] setStroke];
    [hex stroke];

    NSBezierPath *body = [NSBezierPath bezierPathWithRoundedRect:NSMakeRect(point.x - 5, point.y - 5, 10, 8)
                                                         xRadius:2
                                                         yRadius:2];
    body.lineWidth = 1.3;
    [body stroke];
    NSBezierPath *shackle = [NSBezierPath bezierPath];
    [shackle moveToPoint:NSMakePoint(point.x - 4, point.y + 1)];
    [shackle curveToPoint:NSMakePoint(point.x + 4, point.y + 1)
            controlPoint1:NSMakePoint(point.x - 4, point.y + 8)
            controlPoint2:NSMakePoint(point.x + 4, point.y + 8)];
    shackle.lineWidth = 1.3;
    [shackle stroke];
}

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];
    NSRect bounds = NSInsetRect(self.bounds, 2.0, 2.0);

    [NSGraphicsContext saveGraphicsState];
    NSShadow *shadow = [[NSShadow alloc] init];
    shadow.shadowBlurRadius = 22.0;
    shadow.shadowOffset = NSMakeSize(0, -10);
    shadow.shadowColor = [NSColor colorWithWhite:0 alpha:0.58];
    [shadow set];
    NSBezierPath *outer = [NSBezierPath bezierPathWithRoundedRect:bounds xRadius:28 yRadius:28];
    [[NSColor colorWithCalibratedRed:0.09 green:0.12 blue:0.16 alpha:0.98] setFill];
    [outer fill];
    [NSGraphicsContext restoreGraphicsState];

    NSGradient *outerGradient = [[NSGradient alloc] initWithStartingColor:[NSColor colorWithCalibratedRed:0.20 green:0.26 blue:0.33 alpha:1.0]
                                                              endingColor:[NSColor colorWithCalibratedRed:0.035 green:0.043 blue:0.052 alpha:1.0]];
    [outerGradient drawInBezierPath:outer angle:-90.0];
    [[NSColor colorWithCalibratedRed:0.43 green:0.54 blue:0.65 alpha:0.96] setStroke];
    outer.lineWidth = 2.2;
    [outer stroke];

    NSRect innerRect = NSInsetRect(bounds, 26, 26);
    NSBezierPath *inner = [NSBezierPath bezierPathWithRoundedRect:innerRect xRadius:18 yRadius:18];
    NSGradient *innerGradient = [[NSGradient alloc] initWithStartingColor:[NSColor colorWithCalibratedRed:0.075 green:0.09 blue:0.11 alpha:0.98]
                                                              endingColor:[NSColor colorWithCalibratedRed:0.012 green:0.016 blue:0.020 alpha:0.98]];
    [innerGradient drawInBezierPath:inner angle:-90.0];
    [[NSColor colorWithCalibratedRed:0.96 green:0.43 blue:0.06 alpha:0.55] setStroke];
    inner.lineWidth = 1.1;
    [inner stroke];

    [self drawCornerCircuitInRect:innerRect topLeft:YES];
    [self drawCornerCircuitInRect:innerRect topLeft:NO];
    [self drawProtocolBadgeAtPoint:NSMakePoint(NSMinX(innerRect) + 34, NSMaxY(innerRect) - 34)];

    NSRect glowRect = NSMakeRect(NSMidX(bounds) - 30, NSMinY(bounds) + 7, 60, 5);
    NSBezierPath *glow = [NSBezierPath bezierPathWithRoundedRect:glowRect xRadius:3 yRadius:3];
    [NSGraphicsContext saveGraphicsState];
    NSShadow *orange = [[NSShadow alloc] init];
    orange.shadowBlurRadius = 12.0;
    orange.shadowOffset = NSZeroSize;
    orange.shadowColor = [NSColor colorWithCalibratedRed:1.0 green:0.55 blue:0.05 alpha:0.95];
    [orange set];
    [[NSColor colorWithCalibratedRed:1.0 green:0.62 blue:0.06 alpha:0.98] setFill];
    [glow fill];
    [NSGraphicsContext restoreGraphicsState];
}

@end

@interface OverlayWindow : NSWindow
@property(nonatomic, copy) void (^savePositionHandler)(void);
@property(nonatomic, copy) NSString *positionKey;
@property(nonatomic) NSPoint dragStartMouse;
@property(nonatomic) NSPoint dragLastMouse;
@property(nonatomic) NSPoint dragStartOrigin;
@property(nonatomic) NSPoint dragLastOrigin;
@property(nonatomic, copy) NSString *dragRunState;
@end

@implementation OverlayWindow
- (BOOL)canBecomeKeyWindow { return NO; }
- (BOOL)canBecomeMainWindow { return NO; }
- (void)mouseDown:(NSEvent *)event {
    self.dragStartMouse = NSEvent.mouseLocation;
    self.dragLastMouse = self.dragStartMouse;
    self.dragStartOrigin = self.frame.origin;
    self.dragLastOrigin = self.dragStartOrigin;
    self.dragRunState = @"";
}
- (void)mouseDragged:(NSEvent *)event {
    NSPoint current = NSEvent.mouseLocation;
    CGFloat dx = current.x - self.dragStartMouse.x;
    CGFloat dy = current.y - self.dragStartMouse.y;
    NSPoint origin = NSMakePoint(self.dragStartOrigin.x + dx, self.dragStartOrigin.y + dy);
    [self setFrameOrigin:origin];
    CGFloat stepDx = origin.x - self.dragLastOrigin.x;
    self.dragLastMouse = current;
    self.dragLastOrigin = origin;
    if ([self.contentView isKindOfClass:HermesPetView.class] && fabs(stepDx) > 0.5) {
        NSString *nextState = stepDx > 0 ? @"running-right" : @"running-left";
        if (![self.dragRunState isEqualToString:nextState]) {
            self.dragRunState = nextState;
            [(HermesPetView *)self.contentView setAnimationState:nextState];
        }
    }
}
- (void)mouseUp:(NSEvent *)event {
    if ([self.contentView isKindOfClass:HermesPetView.class]) {
        [(HermesPetView *)self.contentView setAnimationState:@"idle"];
    }
    self.dragRunState = @"";
    if (self.savePositionHandler) self.savePositionHandler();
}
@end

@interface AppDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) NSMutableArray<NSWindow *> *windows;
@property(nonatomic, copy) NSString *stateFilePath;
@property(nonatomic, copy) NSString *modeFilePath;
@property(nonatomic, copy) NSString *positionFilePath;
@property(nonatomic, copy) NSString *awakeFilePath;
@property(nonatomic, copy) NSString *stopPosePath;
@property(nonatomic, copy) NSString *stopRunPosePath;
@property(nonatomic, copy) NSString *panelShellPath;
@property(nonatomic, copy) NSString *petName;
@property(nonatomic, copy) NSString *danceBobPath;
@property(nonatomic, copy) NSString *danceStepPath;
@property(nonatomic, copy) NSString *danceHitPath;
@property(nonatomic, copy) NSString *lastStateFileContent;
@property(nonatomic, copy) NSString *lastModeFileContent;
@property(nonatomic, strong) NSTimer *statePollTimer;
@property(nonatomic, strong) NSTimer *activityIdleTimer;
@property(nonatomic, strong) NSTimer *pendingWorkTimer;
@property(nonatomic, strong) NSTimer *ownerProcessTimer;
@property(nonatomic, strong) NSTimer *heartbeatTimer;
@property(nonatomic, strong) NSTimer *stopSignRestoreTimer;
@property(nonatomic, strong) NSTimer *stopSignAnimationTimer;
@property(nonatomic, strong) NSTimer *heroAnimationTimer;
@property(nonatomic, strong) NSTimer *successIdleTimer;
@property(nonatomic, strong) NSDate *stopSignAnimationStart;
@property(nonatomic, strong) NSDate *heroAnimationStart;
@property(nonatomic) NSRect heroStartFrame;
@property(nonatomic) NSRect heroTargetFrame;
@property(nonatomic, strong) NSArray<NSDictionary *> *stopSignAnimationFrames;
@property(nonatomic, strong) NSMutableArray<NSWindow *> *stopSignWindows;
@property(nonatomic, strong) NSWindow *confirmationWindow;
@property(nonatomic, strong) NSWindow *heroStopWindow;
@property(nonatomic, strong) NSWindow *bubbleWindow;
@property(nonatomic, strong) AudioReactiveMonitor *audioReactiveMonitor;
@property(nonatomic, strong) NSDate *lastAudioActiveAt;
@property(nonatomic, copy) NSString *confirmationDecisionFile;
@property(nonatomic, strong) NSMutableArray *eventMonitors;
@property(nonatomic) CFMachPortRef keyboardEventTap;
@property(nonatomic) CFRunLoopSourceRef keyboardRunLoopSource;
@property(nonatomic) BOOL ambientMotion;
@property(nonatomic) BOOL audioReactive;
@property(nonatomic) BOOL dancingActive;
@property(nonatomic) BOOL currentAudioBeatStrong;
@property(nonatomic) CGFloat normalScale;
@property(nonatomic) CGFloat danceScale;
@property(nonatomic) CGFloat currentDanceScale;
@property(nonatomic) CGFloat danceEnergy;
@property(nonatomic) CGFloat dancePulse;
@property(nonatomic) NSTimeInterval lastDanceBeatAt;
@property(nonatomic) NSTimeInterval estimatedDanceBeatInterval;
@property(nonatomic) NSTimeInterval lastDanceFrameAt;
@property(nonatomic, strong) NSTimer *danceVisualTimer;
@property(nonatomic) pid_t ownerPid;
@property(nonatomic, copy) NSString *heartbeatFilePath;
@property(nonatomic) NSTimeInterval heartbeatTimeout;
@property(nonatomic) BOOL hasLaunchFrame;
@property(nonatomic) NSRect launchFrame;
- (void)saveWindowPositions;
- (void)handleKeyboardKeyCode:(int64_t)keyCode;
- (void)playStopSignEffect;
- (void)showConfirmationHeroOnScreen:(NSScreen *)screen;
- (void)stepHeroAnimation;
- (void)showFinalDeletionConfirmationOnScreen:(NSScreen *)screen;
- (NSRect)guardConfirmationFrameOnScreen:(NSScreen *)screen;
- (NSSize)guardConfirmationAssetSize;
- (void)showDeletionConfirmation:(NSString *)decisionFile;
- (void)updateBubbleForState:(NSString *)state;
- (void)updateBubbleForState:(NSString *)state message:(NSString *)message;
- (void)clearTransientGuardWindows;
- (void)scheduleSuccessReturnIfNeeded:(NSString *)state;
- (void)handleAudioRMS:(double)rms beat:(BOOL)beat;
- (void)setDancingActive:(BOOL)active beat:(BOOL)beat;
- (void)tickDanceVisuals;
- (NSScreen *)screenForRect:(NSRect)rect fallback:(NSScreen *)fallback;
- (CGRect)frontWindowBoundsFromWindowListForProcess:(pid_t)pid found:(BOOL *)found;
- (NSRect)frontWindowLaunchFrameWithPetSize:(NSSize)petSize margin:(CGFloat)margin found:(BOOL *)found;
@end

static CGEventRef KeyboardEventTapCallback(CGEventTapProxy proxy,
                                           CGEventType type,
                                           CGEventRef event,
                                           void *refcon) {
    AppDelegate *delegate = (__bridge AppDelegate *)refcon;
    if (type == kCGEventTapDisabledByTimeout || type == kCGEventTapDisabledByUserInput) {
        if (delegate.keyboardEventTap) {
            CGEventTapEnable(delegate.keyboardEventTap, true);
        }
        return event;
    }
    if (type != kCGEventKeyDown) return event;

    int64_t keyCode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode);
    dispatch_async(dispatch_get_main_queue(), ^{
        [delegate handleKeyboardKeyCode:keyCode];
    });
    return event;
}

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
    self.windows = [NSMutableArray array];

    NSString *spritesheet = ArgumentValue(@"--spritesheet") ?: DefaultSpritesheetPath();
    NSString *state = ArgumentValue(@"--state") ?: @"idle";
    self.stateFilePath = ArgumentValue(@"--state-file") ?: DefaultStateFile;
    self.modeFilePath = ArgumentValue(@"--mode-file") ?: DefaultModeFile;
    self.positionFilePath = ArgumentValue(@"--position-file") ?: DefaultPositionFile;
    self.awakeFilePath = ArgumentValue(@"--awake-file") ?: DefaultAwakeFile;
    self.stopPosePath = ArgumentValue(@"--stop-pose") ?: (DefaultHermesPetAssetPath(@"guard-peek-stop-no-panel.png") ?: @"");
    self.stopRunPosePath = ArgumentValue(@"--stop-run-pose") ?: (DefaultHermesPetAssetPath(@"stop-sign-run-front-strip.png") ?: @"");
    self.panelShellPath = ArgumentValue(@"--panel-shell") ?: @"";
    self.petName = ArgumentValue(@"--pet-name") ?: @"Hermes Pet";
    if (!self.panelShellPath.length && self.stopPosePath.length) {
        NSString *assetDir = self.stopPosePath.stringByDeletingLastPathComponent;
        self.panelShellPath = [assetDir stringByAppendingPathComponent:@"panel-shell.png"];
    }
    if (self.panelShellPath.length && ![NSFileManager.defaultManager fileExistsAtPath:self.panelShellPath.stringByExpandingTildeInPath]) {
        self.panelShellPath = @"";
    }
    self.danceBobPath = ArgumentValue(@"--dance-bob") ?: @"";
    self.danceStepPath = ArgumentValue(@"--dance-step") ?: @"";
    self.danceHitPath = ArgumentValue(@"--dance-hit") ?: @"";
    if (!self.danceBobPath.length && self.stopPosePath.length) {
        NSString *assetDir = self.stopPosePath.stringByDeletingLastPathComponent;
        self.danceBobPath = [assetDir stringByAppendingPathComponent:@"dance-bob-strip.png"];
        self.danceStepPath = [assetDir stringByAppendingPathComponent:@"dance-step-strip.png"];
        self.danceHitPath = [assetDir stringByAppendingPathComponent:@"dance-hit-strip.png"];
    }
    self.ambientMotion = HasArgument(@"--ambient-motion");
    self.audioReactive = HasArgument(@"--audio-reactive");
    self.ownerPid = (pid_t)(ArgumentValue(@"--owner-pid") ?: @"0").intValue;
    self.heartbeatFilePath = ArgumentValue(@"--heartbeat-file") ?: @"";
    self.heartbeatTimeout = (ArgumentValue(@"--heartbeat-timeout") ?: @"4").doubleValue;
    CGFloat scale = (ArgumentValue(@"--scale") ?: @"0.55").doubleValue;
    self.normalScale = scale;
    self.danceScale = scale * 1.36;
    self.currentDanceScale = scale;
    self.estimatedDanceBeatInterval = 0.50;
    CGFloat margin = (ArgumentValue(@"--margin") ?: @"28").doubleValue;
    BOOL allScreens = !HasArgument(@"--main-screen-only");
    BOOL clickable = HasArgument(@"--clickable") || [self currentModeIsUnlocked];
    self.hasLaunchFrame = NO;
    self.launchFrame = NSZeroRect;

    CGImageRef atlas = [self loadAtlas:spritesheet];
    if (!atlas) {
        fprintf(stderr, "Could not load spritesheet at %s\n", spritesheet.UTF8String);
        [NSApp terminate:nil];
        return;
    }

    NSScreen *fallbackScreen = NSScreen.mainScreen ?: NSScreen.screens.firstObject;
    if (!allScreens) {
        NSSize petSize = NSMakeSize(CellWidth * scale, CellHeight * scale);
        NSString *originX = ArgumentValue(@"--origin-x");
        NSString *originY = ArgumentValue(@"--origin-y");
        if (originX.length && originY.length) {
            self.launchFrame = NSMakeRect(originX.doubleValue, originY.doubleValue, petSize.width, petSize.height);
            self.hasLaunchFrame = YES;
        } else if (HasArgument(@"--anchor-front-window")) {
            BOOL found = NO;
            NSRect frame = [self frontWindowLaunchFrameWithPetSize:petSize margin:margin found:&found];
            if (found) {
                self.launchFrame = frame;
                self.hasLaunchFrame = YES;
            }
        }
    }

    NSScreen *targetScreen = self.hasLaunchFrame ? [self screenForRect:self.launchFrame fallback:fallbackScreen] : fallbackScreen;
    NSArray<NSScreen *> *screens = allScreens ? NSScreen.screens : @[targetScreen ?: fallbackScreen];
    for (NSScreen *screen in screens) {
        [self createWindowOnScreen:screen atlas:atlas state:state scale:scale margin:margin clickable:clickable];
    }
    CGImageRelease(atlas);

    self.statePollTimer = [NSTimer scheduledTimerWithTimeInterval:0.20
                                                           target:self
                                                         selector:@selector(checkControlFiles)
                                                         userInfo:nil
                                                          repeats:YES];
    if (self.ownerPid > 1) {
        self.ownerProcessTimer = [NSTimer scheduledTimerWithTimeInterval:0.20
                                                                  target:self
                                                                selector:@selector(checkOwnerProcess)
                                                                userInfo:nil
                                                                 repeats:YES];
    }
    if (self.heartbeatFilePath.length) {
        self.heartbeatTimer = [NSTimer scheduledTimerWithTimeInterval:0.10
                                                               target:self
                                                             selector:@selector(checkHeartbeat)
                                                             userInfo:nil
                                                              repeats:YES];
    }
    [self installActivityMonitors];
    if (self.audioReactive) {
        __weak typeof(self) weakSelf = self;
        self.audioReactiveMonitor = [[AudioReactiveMonitor alloc] initWithLevelHandler:^(double rms, BOOL beat) {
            [weakSelf handleAudioRMS:rms beat:beat];
        }];
        [self.audioReactiveMonitor start];
    }
}

- (void)dealloc {
    [self.audioReactiveMonitor stop];
    if (self.keyboardRunLoopSource) CFRelease(self.keyboardRunLoopSource);
    if (self.keyboardEventTap) CFRelease(self.keyboardEventTap);
}

- (void)checkOwnerProcess {
    if (self.ownerPid <= 1) return;
    if (kill(self.ownerPid, 0) == 0 && ![self ownerProcessIsStopped]) return;
    [NSApp terminate:nil];
}

- (BOOL)ownerProcessIsStopped {
    if (self.ownerPid <= 1) return NO;
    int mib[4] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, self.ownerPid};
    struct kinfo_proc info;
    size_t size = sizeof(info);
    memset(&info, 0, sizeof(info));
    if (sysctl(mib, 4, &info, &size, NULL, 0) != 0 || size == 0) return NO;
    return info.kp_proc.p_stat == SSTOP;
}

- (void)checkHeartbeat {
    if (!self.heartbeatFilePath.length) return;
    NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:self.heartbeatFilePath
                                                                              error:nil];
    NSDate *modified = attributes[NSFileModificationDate];
    if (!modified) {
        [NSApp terminate:nil];
        return;
    }
    if (-modified.timeIntervalSinceNow > MAX(0.25, self.heartbeatTimeout)) {
        [NSApp terminate:nil];
    }
}

- (CGImageRef)loadAtlas:(NSString *)path {
    NSString *expandedPath = path.stringByExpandingTildeInPath;
    NSImage *image = [[NSImage alloc] initWithContentsOfFile:expandedPath];
    if (!image) return nil;

    NSRect rect = NSMakeRect(0, 0, image.size.width, image.size.height);
    CGImageRef cgImage = [image CGImageForProposedRect:&rect context:nil hints:nil];
    return cgImage ? CGImageRetain(cgImage) : nil;
}

- (NSPoint)convertAccessibilityTopLeftPoint:(CGPoint)point elementSize:(NSSize)size {
    NSScreen *mainScreen = NSScreen.mainScreen ?: NSScreen.screens.firstObject;
    CGFloat mainTop = mainScreen ? NSMaxY(mainScreen.frame) : 0.0;
    CGFloat mainLeft = mainScreen ? NSMinX(mainScreen.frame) : 0.0;
    return NSMakePoint(mainLeft + point.x, mainTop - point.y - size.height);
}

- (NSScreen *)screenForPoint:(NSPoint)point fallback:(NSScreen *)fallback {
    NSScreen *nearest = fallback ?: NSScreen.mainScreen ?: NSScreen.screens.firstObject;
    CGFloat nearestDistance = CGFLOAT_MAX;
    for (NSScreen *screen in NSScreen.screens) {
        NSRect frame = screen.frame;
        if (NSPointInRect(point, frame)) return screen;
        CGFloat dx = point.x - NSMidX(frame);
        CGFloat dy = point.y - NSMidY(frame);
        CGFloat distance = dx * dx + dy * dy;
        if (distance < nearestDistance) {
            nearestDistance = distance;
            nearest = screen;
        }
    }
    return nearest;
}

- (NSScreen *)screenForRect:(NSRect)rect fallback:(NSScreen *)fallback {
    return [self screenForPoint:NSMakePoint(NSMidX(rect), NSMidY(rect)) fallback:fallback];
}

- (CGRect)frontWindowBoundsFromWindowListForProcess:(pid_t)pid found:(BOOL *)found {
    if (found) *found = NO;
    CFArrayRef rawWindows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                                                       kCGNullWindowID);
    if (!rawWindows) return CGRectZero;

    NSArray *windows = CFBridgingRelease(rawWindows);
    for (NSDictionary *window in windows) {
        NSNumber *ownerPID = window[(NSString *)kCGWindowOwnerPID];
        NSNumber *layer = window[(NSString *)kCGWindowLayer];
        NSDictionary *boundsDict = window[(NSString *)kCGWindowBounds];
        if (ownerPID.intValue != pid || layer.intValue != 0 || !boundsDict) continue;

        CGRect bounds = CGRectZero;
        if (!CGRectMakeWithDictionaryRepresentation((CFDictionaryRef)boundsDict, &bounds)) continue;
        if (bounds.size.width < 80.0 || bounds.size.height < 80.0) continue;

        if (found) *found = YES;
        return bounds;
    }
    return CGRectZero;
}

- (NSRect)frontWindowLaunchFrameWithPetSize:(NSSize)petSize margin:(CGFloat)margin found:(BOOL *)found {
    if (found) *found = NO;
    NSRunningApplication *frontApp = NSWorkspace.sharedWorkspace.frontmostApplication;
    if (!frontApp || frontApp.processIdentifier == getpid()) return NSZeroRect;

    BOOL windowListFound = NO;
    CGRect windowBounds = [self frontWindowBoundsFromWindowListForProcess:frontApp.processIdentifier found:&windowListFound];
    if (!windowListFound) {
        AXUIElementRef app = AXUIElementCreateApplication(frontApp.processIdentifier);
        if (!app) return NSZeroRect;

        AXUIElementRef window = NULL;
        AXError windowError = AXUIElementCopyAttributeValue(app, kAXFocusedWindowAttribute, (CFTypeRef *)&window);
        if (windowError != kAXErrorSuccess || !window) {
            CFArrayRef windows = NULL;
            if (AXUIElementCopyAttributeValue(app, kAXWindowsAttribute, (CFTypeRef *)&windows) == kAXErrorSuccess && windows && CFArrayGetCount(windows) > 0) {
                window = (AXUIElementRef)CFRetain(CFArrayGetValueAtIndex(windows, 0));
            }
            if (windows) CFRelease(windows);
        }
        CFRelease(app);
        if (!window) return NSZeroRect;

        AXValueRef positionValue = NULL;
        AXValueRef sizeValue = NULL;
        CGPoint windowPosition = CGPointZero;
        CGSize windowSize = CGSizeZero;
        BOOL ok = AXUIElementCopyAttributeValue(window, kAXPositionAttribute, (CFTypeRef *)&positionValue) == kAXErrorSuccess &&
                  AXUIElementCopyAttributeValue(window, kAXSizeAttribute, (CFTypeRef *)&sizeValue) == kAXErrorSuccess &&
                  positionValue &&
                  sizeValue &&
                  AXValueGetValue(positionValue, kAXValueCGPointType, &windowPosition) &&
                  AXValueGetValue(sizeValue, kAXValueCGSizeType, &windowSize);
        if (positionValue) CFRelease(positionValue);
        if (sizeValue) CFRelease(sizeValue);
        CFRelease(window);
        if (!ok || windowSize.width <= 0 || windowSize.height <= 0) return NSZeroRect;
        windowBounds = CGRectMake(windowPosition.x, windowPosition.y, windowSize.width, windowSize.height);
    }

    if (windowBounds.size.width <= 0 || windowBounds.size.height <= 0) return NSZeroRect;
    CGPoint petTopLeft = CGPointMake(
        windowBounds.origin.x + MAX(0.0, windowBounds.size.width - petSize.width - margin),
        windowBounds.origin.y + MAX(0.0, windowBounds.size.height - petSize.height - margin)
    );
    NSPoint origin = [self convertAccessibilityTopLeftPoint:petTopLeft elementSize:petSize];
    if (found) *found = YES;
    return NSMakeRect(origin.x, origin.y, petSize.width, petSize.height);
}

- (void)createWindowOnScreen:(NSScreen *)screen
                       atlas:(CGImageRef)atlas
                       state:(NSString *)state
                       scale:(CGFloat)scale
                      margin:(CGFloat)margin
                   clickable:(BOOL)clickable {
    CGFloat width = CellWidth * scale;
    CGFloat height = CellHeight * scale;
    NSRect visible = screen.visibleFrame;
    NSString *key = [self positionKeyForScreen:screen];
    NSRect frame = NSMakeRect(
        NSMaxX(visible) - width - margin,
        NSMinY(visible) + margin,
        width,
        height
    );
    NSValue *savedOrigin = [self savedPositions][key];
    if (savedOrigin) {
        frame.origin = savedOrigin.pointValue;
    }
    if (self.hasLaunchFrame) {
        frame.origin = self.launchFrame.origin;
    }

    OverlayWindow *window = [[OverlayWindow alloc] initWithContentRect:frame
                                                             styleMask:NSWindowStyleMaskBorderless
                                                               backing:NSBackingStoreBuffered
                                                                defer:NO
                                                                screen:screen];
    __weak typeof(self) weakSelf = self;
    window.savePositionHandler = ^{
        [weakSelf saveWindowPositions];
    };
    window.positionKey = key;
    window.backgroundColor = NSColor.clearColor;
    window.opaque = NO;
    window.hasShadow = NO;
    window.animationBehavior = NSWindowAnimationBehaviorNone;
    window.level = NSFloatingWindowLevel;
    window.ignoresMouseEvents = !clickable;
    window.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                                NSWindowCollectionBehaviorFullScreenAuxiliary |
                                NSWindowCollectionBehaviorStationary;
    HermesPetView *petView = [[HermesPetView alloc] initWithAtlas:atlas
                                                  stateName:state
                                             ambientMotion:self.ambientMotion];
    [petView setDanceBobPath:self.danceBobPath stepPath:self.danceStepPath hitPath:self.danceHitPath];
    window.contentView = petView;
    [window orderFrontRegardless];
    [self.windows addObject:window];
}

- (void)checkControlFiles {
    [self checkModeFile];
    [self checkStateFile];
}

- (void)checkStateFile {
    if (!self.stateFilePath.length) return;

    NSError *error = nil;
    NSString *content = [NSString stringWithContentsOfFile:self.stateFilePath
                                                  encoding:NSUTF8StringEncoding
                                                     error:&error];
    if (!content.length || [content isEqualToString:self.lastStateFileContent]) return;

    self.lastStateFileContent = content;
    NSArray<NSString *> *parts = [content componentsSeparatedByCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSString *state = parts.firstObject;
    NSString *message = @"";
    if (parts.count > 2) {
        NSRange range = NSMakeRange(2, parts.count - 2);
        message = [[parts subarrayWithRange:range] componentsJoinedByString:@" "];
    }
    if ([state isEqualToString:@"confirm-delete"] && parts.count >= 2) {
        [self showDeletionConfirmation:parts[1]];
        return;
    }
    if ([state isEqualToString:@"stop-sign"]) {
        [self updateBubbleForState:state message:message];
        [self playStopSignEffect];
        return;
    }
    if (!IsKnownState(state)) return;
    [self clearTransientGuardWindows];
    if (![state isEqualToString:@"idle"] && ![state isEqualToString:@"waving"] && ![state isEqualToString:@"dancing"]) {
        [self setDancingActive:NO beat:NO];
    }

    for (NSWindow *window in self.windows) {
        if ([window.contentView isKindOfClass:HermesPetView.class]) {
            [(HermesPetView *)window.contentView setAnimationState:state];
        }
    }
    [self updateBubbleForState:state message:message];
    [self scheduleSuccessReturnIfNeeded:state];
}

- (void)setAllWindowsState:(NSString *)state {
    if (!IsKnownState(state)) return;
    for (NSWindow *window in self.windows) {
        if ([window.contentView isKindOfClass:HermesPetView.class]) {
            [(HermesPetView *)window.contentView setAnimationState:state];
        }
    }
    [self updateBubbleForState:state];
    [self scheduleSuccessReturnIfNeeded:state];
}

- (void)scheduleSuccessReturnIfNeeded:(NSString *)state {
    [self.successIdleTimer invalidate];
    self.successIdleTimer = nil;
    if (![state isEqualToString:@"success"]) return;
    self.successIdleTimer = [NSTimer scheduledTimerWithTimeInterval:2.4
                                                             target:self
                                                           selector:@selector(returnToQuietIdle)
                                                           userInfo:nil
                                                            repeats:NO];
}

- (NSString *)primaryPetState {
    for (NSWindow *window in self.windows) {
        if ([window.contentView isKindOfClass:HermesPetView.class]) {
            return ((HermesPetView *)window.contentView).stateName ?: @"idle";
        }
    }
    return @"idle";
}

- (BOOL)audioMayControlPet {
    NSString *state = [self primaryPetState];
    return [state isEqualToString:@"idle"] ||
           [state isEqualToString:@"waving"] ||
           [state isEqualToString:@"dancing"];
}

- (void)resizePetWindowsToScale:(CGFloat)scale beat:(BOOL)beat {
    CGFloat pulse = beat ? 1.10 : 1.0;
    CGFloat width = CellWidth * scale * pulse;
    CGFloat height = CellHeight * scale * pulse;
    for (NSWindow *window in self.windows) {
        NSRect frame = window.frame;
        CGFloat centerX = NSMidX(frame);
        CGFloat bottomY = NSMinY(frame);
        NSRect newFrame = NSMakeRect(centerX - width / 2.0, bottomY, width, height);
        [window setFrame:newFrame display:YES animate:NO];
    }
}

- (void)ensureDanceVisualTimer {
    if (self.danceVisualTimer) return;
    self.lastDanceFrameAt = 0.0;
    self.danceVisualTimer = [NSTimer scheduledTimerWithTimeInterval:1.0 / 30.0
                                                             target:self
                                                           selector:@selector(tickDanceVisuals)
                                                           userInfo:nil
                                                            repeats:YES];
}

- (void)stopDanceVisualTimer {
    [self.danceVisualTimer invalidate];
    self.danceVisualTimer = nil;
    self.dancePulse = 0.0;
    self.danceEnergy = 0.0;
    self.lastDanceFrameAt = 0.0;
}

- (void)advanceDanceFramesStrongBeat:(BOOL)strongBeat {
    for (NSWindow *window in self.windows) {
        if ([window.contentView isKindOfClass:HermesPetView.class]) {
            [(HermesPetView *)window.contentView advanceDanceFrameWithStrongBeat:strongBeat];
        }
    }
}

- (void)tickDanceVisuals {
    if (!self.dancingActive) return;

    NSTimeInterval now = NSDate.date.timeIntervalSince1970;
    NSTimeInterval beatInterval = MIN(0.82, MAX(0.34, self.estimatedDanceBeatInterval ?: 0.50));
    NSTimeInterval frameInterval = MIN(0.16, MAX(0.085, beatInterval / 4.0));
    if (self.lastDanceFrameAt <= 0.0 || now - self.lastDanceFrameAt >= frameInterval) {
        self.lastDanceFrameAt = now;
        [self advanceDanceFramesStrongBeat:NO];
    }

    self.dancePulse *= 0.82;
    CGFloat targetScale = self.danceScale * (1.0 + self.danceEnergy * 0.055 + self.dancePulse * 0.085);
    self.currentDanceScale = self.currentDanceScale + (targetScale - self.currentDanceScale) * 0.34;
    [self resizePetWindowsToScale:self.currentDanceScale beat:NO];
}

- (void)handleAudioRMS:(double)rms beat:(BOOL)beat {
    if (!self.audioReactive || ![self isAwake]) return;
    NSTimeInterval now = NSDate.date.timeIntervalSince1970;
    BOOL active = rms > AudioActiveRMSThreshold;
    CGFloat normalizedEnergy = MIN(1.0, MAX(0.0, (rms - AudioActiveRMSThreshold) / 0.12));
    self.danceEnergy = self.danceEnergy * 0.78 + normalizedEnergy * 0.22;
    if (active) {
        self.lastAudioActiveAt = NSDate.date;
        if ([self audioMayControlPet]) {
            if (beat) {
                if (self.lastDanceBeatAt > 0.0) {
                    NSTimeInterval interval = now - self.lastDanceBeatAt;
                    if (interval > 0.26 && interval < 1.15) {
                        self.estimatedDanceBeatInterval = self.estimatedDanceBeatInterval * 0.78 + interval * 0.22;
                    }
                }
                self.lastDanceBeatAt = now;
                self.dancePulse = 1.0;
            }
            self.currentAudioBeatStrong = beat && rms > 0.055;
            [self setDancingActive:YES beat:beat];
        }
        return;
    }

    if (self.dancingActive && (!self.lastAudioActiveAt || now - self.lastAudioActiveAt.timeIntervalSince1970 > AudioStopSilenceSeconds)) {
        [self setDancingActive:NO beat:NO];
    }
}

- (void)setDancingActive:(BOOL)active beat:(BOOL)beat {
    if (active) {
        if (![self audioMayControlPet]) return;
        BOOL wasDancing = self.dancingActive;
        self.dancingActive = YES;
        [self ensureDanceVisualTimer];
        if (!wasDancing) {
            self.currentDanceScale = self.normalScale;
            self.lastDanceFrameAt = 0.0;
        }
        for (NSWindow *window in self.windows) {
            if ([window.contentView isKindOfClass:HermesPetView.class]) {
                HermesPetView *view = (HermesPetView *)window.contentView;
                if (![view.stateName isEqualToString:@"dancing"]) {
                    [view setAnimationState:@"dancing"];
                }
                if (beat) [view advanceDanceFrameWithStrongBeat:self.currentAudioBeatStrong];
            }
        }
        return;
    }

    if (!self.dancingActive) return;
    self.dancingActive = NO;
    [self stopDanceVisualTimer];
    self.lastDanceBeatAt = 0.0;
    self.estimatedDanceBeatInterval = 0.50;
    self.currentDanceScale = self.normalScale;
    [self resizePetWindowsToScale:self.normalScale beat:NO];
    for (NSWindow *window in self.windows) {
        if ([window.contentView isKindOfClass:HermesPetView.class]) {
            HermesPetView *view = (HermesPetView *)window.contentView;
            if ([view.stateName isEqualToString:@"dancing"]) {
                [view setAnimationState:@"idle"];
            }
        }
    }
}

- (void)updateBubbleForState:(NSString *)state {
    [self updateBubbleForState:state message:nil];
}

- (void)updateBubbleForState:(NSString *)state message:(NSString *)message {
    NSString *text = nil;
    NSString *trimmedMessage = [message stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (trimmedMessage.length) {
        text = trimmedMessage;
    } else if ([state isEqualToString:@"waiting"]) {
        text = @"thinking...";
    } else if ([state isEqualToString:@"running"] || [state isEqualToString:@"review"]) {
        text = @"working...";
    } else if ([state isEqualToString:@"failed"]) {
        text = @"hmm...";
    } else if ([state isEqualToString:@"success"]) {
        text = @"success";
    } else if ([state isEqualToString:@"stop-sign"]) {
        text = @"pause";
    }

    if (!text.length || self.windows.count == 0) {
        [self.bubbleWindow orderOut:nil];
        self.bubbleWindow = nil;
        return;
    }

    NSWindow *petWindow = self.windows.firstObject;
    NSRect petFrame = petWindow.frame;
    CGFloat width = MIN(220.0, MAX(112.0, text.length * 7.8 + 28.0));
    CGFloat height = 34.0;
    NSRect frame = NSMakeRect(NSMidX(petFrame) - width / 2.0,
                              NSMaxY(petFrame) + 6.0,
                              width,
                              height);

    if (!self.bubbleWindow) {
        NSWindow *window = [[NSWindow alloc] initWithContentRect:frame
                                                       styleMask:NSWindowStyleMaskBorderless
                                                         backing:NSBackingStoreBuffered
                                                           defer:NO
                                                          screen:petWindow.screen];
        window.backgroundColor = NSColor.clearColor;
        window.opaque = NO;
        window.hasShadow = NO;
        window.animationBehavior = NSWindowAnimationBehaviorNone;
        window.level = NSFloatingWindowLevel + 1;
        window.ignoresMouseEvents = YES;
        window.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                                    NSWindowCollectionBehaviorFullScreenAuxiliary |
                                    NSWindowCollectionBehaviorStationary;
        window.contentView = [[BubbleView alloc] initWithText:text];
        self.bubbleWindow = window;
    } else {
        [self.bubbleWindow setFrame:frame display:YES animate:NO];
        if ([self.bubbleWindow.contentView isKindOfClass:BubbleView.class]) {
            ((BubbleView *)self.bubbleWindow.contentView).text = text;
        }
    }
    [self.bubbleWindow orderFrontRegardless];
}

- (void)playStopSignEffect {
    if (![self isAwake]) return;

    [self.activityIdleTimer invalidate];
    [self.stopSignRestoreTimer invalidate];
    [self.stopSignAnimationTimer invalidate];
    [self clearStopSignWindows];

    [self setAllWindowsState:@"running"];

    NSMutableArray<NSDictionary *> *frames = [NSMutableArray array];
    for (NSWindow *window in self.windows) {
        NSScreen *screen = window.screen ?: NSScreen.mainScreen;
        NSRect original = window.frame;
        NSRect visible = screen.visibleFrame;
        CGFloat targetWidth = original.size.width * 1.9;
        CGFloat targetHeight = original.size.height * 1.9;
        NSRect target = NSMakeRect(NSMidX(visible) - targetWidth - 46.0,
                                   NSMidY(visible) - targetHeight / 2.0,
                                   targetWidth,
                                   targetHeight);
        [frames addObject:@{
            @"window": window,
            @"original": [NSValue valueWithRect:original],
            @"target": [NSValue valueWithRect:target]
        }];
        [self showStopSignOnScreen:screen];
    }
    self.stopSignAnimationFrames = frames;
    self.stopSignAnimationStart = [NSDate date];
    self.stopSignAnimationTimer = [NSTimer scheduledTimerWithTimeInterval:1.0 / 60.0
                                                                  repeats:YES
                                                                    block:^(NSTimer *timer) {
        [self stepStopSignAnimation];
    }];

    [self performSelector:@selector(switchStopSignToFailedPose) withObject:nil afterDelay:0.45];

    self.stopSignRestoreTimer = [NSTimer scheduledTimerWithTimeInterval:2.7 repeats:NO block:^(NSTimer *timer) {
        [self clearStopSignWindows];
        [self setAllWindowsState:@"idle"];
    }];
}

- (void)stepStopSignAnimation {
    NSTimeInterval elapsed = -[self.stopSignAnimationStart timeIntervalSinceNow];
    CGFloat progress = 0.0;
    BOOL holdForConfirmation = self.confirmationDecisionFile.length > 0;
    if (elapsed < 0.55) {
        progress = [self easeOutCubic:elapsed / 0.55];
    } else if (holdForConfirmation) {
        progress = 1.0;
    } else if (elapsed < 2.15) {
        progress = 1.0;
    } else if (elapsed < 2.70) {
        progress = 1.0 - [self easeInCubic:(elapsed - 2.15) / 0.55];
    } else {
        progress = 0.0;
        [self.stopSignAnimationTimer invalidate];
        self.stopSignAnimationTimer = nil;
    }

    for (NSDictionary *entry in self.stopSignAnimationFrames) {
        NSWindow *window = entry[@"window"];
        NSRect original = [entry[@"original"] rectValue];
        NSRect target = [entry[@"target"] rectValue];
        NSRect frame = [self interpolateRectFrom:original to:target progress:progress];
        [window setFrame:frame display:YES animate:NO];
    }
}

- (CGFloat)easeOutCubic:(CGFloat)t {
    t = MIN(1.0, MAX(0.0, t));
    CGFloat inverse = 1.0 - t;
    return 1.0 - inverse * inverse * inverse;
}

- (CGFloat)easeInCubic:(CGFloat)t {
    t = MIN(1.0, MAX(0.0, t));
    return t * t * t;
}

- (NSRect)interpolateRectFrom:(NSRect)from to:(NSRect)to progress:(CGFloat)progress {
    return NSMakeRect(
        from.origin.x + (to.origin.x - from.origin.x) * progress,
        from.origin.y + (to.origin.y - from.origin.y) * progress,
        from.size.width + (to.size.width - from.size.width) * progress,
        from.size.height + (to.size.height - from.size.height) * progress
    );
}

- (void)switchStopSignToFailedPose {
    [self setAllWindowsState:@"failed"];
}

- (void)showStopSignOnScreen:(NSScreen *)screen {
    if (!self.stopSignWindows) self.stopSignWindows = [NSMutableArray array];

    NSRect visible = screen.visibleFrame;
    CGFloat size = MIN(MIN(visible.size.width, visible.size.height) * 0.22, 205.0);
    size = MAX(size, 145.0);
    CGFloat x = NSMidX(visible) - 12.0;
    CGFloat y = NSMidY(visible) - size / 2.0;
    NSRect signFrame = NSMakeRect(x, y, size, size);

    NSWindow *signWindow = [[NSWindow alloc] initWithContentRect:signFrame
                                                       styleMask:NSWindowStyleMaskBorderless
                                                         backing:NSBackingStoreBuffered
                                                           defer:NO
                                                          screen:screen];
    signWindow.backgroundColor = NSColor.clearColor;
    signWindow.opaque = NO;
    signWindow.hasShadow = NO;
    signWindow.animationBehavior = NSWindowAnimationBehaviorNone;
    signWindow.level = NSFloatingWindowLevel + 1;
    signWindow.ignoresMouseEvents = YES;
    signWindow.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                                    NSWindowCollectionBehaviorFullScreenAuxiliary |
                                    NSWindowCollectionBehaviorStationary;
    signWindow.contentView = [[StopSignView alloc] initWithFrame:NSMakeRect(0, 0, size, size)];
    [signWindow orderFrontRegardless];
    [self.stopSignWindows addObject:signWindow];
}

- (void)showConfirmationHeroOnScreen:(NSScreen *)screen {
    [self.heroStopWindow orderOut:nil];
    self.heroStopWindow = nil;
    [self.heroAnimationTimer invalidate];
    self.heroAnimationTimer = nil;

    CGImageRef atlas = nil;
    NSRect petFrame = NSZeroRect;
    for (NSWindow *window in self.windows) {
        if ([window.contentView isKindOfClass:HermesPetView.class]) {
            atlas = ((HermesPetView *)window.contentView).atlas;
            petFrame = window.frame;
            [window orderOut:nil];
            break;
        }
    }
    if (!atlas) return;

    NSRect frame = [self guardConfirmationFrameOnScreen:screen];
    CGFloat width = frame.size.width;
    CGFloat height = frame.size.height;
    CGFloat startWidth = MAX(petFrame.size.width, width * 0.24);
    CGFloat startHeight = startWidth * (height / width);
    NSRect startFrame = NSMakeRect(NSMidX(petFrame) - startWidth / 2.0,
                                   NSMidY(petFrame) - startHeight / 2.0,
                                   startWidth,
                                   startHeight);
    NSWindow *window = [[NSWindow alloc] initWithContentRect:frame
                                                   styleMask:NSWindowStyleMaskBorderless
                                                     backing:NSBackingStoreBuffered
                                                       defer:NO
                                                      screen:screen];
    window.backgroundColor = NSColor.clearColor;
    window.opaque = NO;
    window.hasShadow = NO;
    window.animationBehavior = NSWindowAnimationBehaviorNone;
    window.level = NSFloatingWindowLevel + 3;
    window.ignoresMouseEvents = YES;
    window.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                                NSWindowCollectionBehaviorFullScreenAuxiliary |
                                NSWindowCollectionBehaviorStationary;
    window.contentView = [[StopHeroView alloc] initWithAtlas:atlas
                                                stopPosePath:self.stopPosePath
                                                 runPosePath:self.stopRunPosePath];
    [window setFrame:startFrame display:NO animate:NO];
    self.heroStopWindow = window;
    self.heroStartFrame = startFrame;
    self.heroTargetFrame = frame;
    self.heroAnimationStart = [NSDate date];
    [window orderFrontRegardless];
    self.heroAnimationTimer = [NSTimer scheduledTimerWithTimeInterval:1.0 / 60.0
                                                               target:self
                                                             selector:@selector(stepHeroAnimation)
                                                             userInfo:nil
                                                              repeats:YES];
}

- (void)stepHeroAnimation {
    NSTimeInterval elapsed = -[self.heroAnimationStart timeIntervalSinceNow];
    CGFloat progress = [self easeOutCubic:elapsed / 1.12];
    NSRect frame = [self interpolateRectFrom:self.heroStartFrame
                                          to:self.heroTargetFrame
                                    progress:progress];
    [self.heroStopWindow setFrame:frame display:YES animate:NO];
    if (progress >= 1.0) {
        [self.heroAnimationTimer invalidate];
        self.heroAnimationTimer = nil;
        if ([self.heroStopWindow.contentView respondsToSelector:@selector(freezeStopPoseAtMaxSize)]) {
            [(StopHeroView *)self.heroStopWindow.contentView freezeStopPoseAtMaxSize];
        }
        NSScreen *screen = self.heroStopWindow.screen ?: self.windows.firstObject.screen ?: NSScreen.mainScreen ?: NSScreen.screens.firstObject;
        [self.heroStopWindow orderOut:nil];
        self.heroStopWindow = nil;
        [self showFinalDeletionConfirmationOnScreen:screen];
    }
}

- (NSRect)guardConfirmationFrameOnScreen:(NSScreen *)screen {
    NSRect visible = screen.visibleFrame;
    NSRect display = screen.frame;
    NSSize assetSize = [self guardConfirmationAssetSize];
    CGFloat assetWidth = assetSize.width;
    CGFloat assetHeight = assetSize.height;
    CGFloat width = MIN(690.0, visible.size.width - 56.0);
    CGFloat height = width * (assetHeight / assetWidth);
    if (height > visible.size.height - 56.0) {
        height = visible.size.height - 56.0;
        width = height * (assetWidth / assetHeight);
    }
    CGFloat x = NSMidX(display) - width / 2.0;
    CGFloat y = NSMidY(display) - height / 2.0;
    x = MIN(MAX(x, NSMinX(visible) + 16.0), NSMaxX(visible) - width - 16.0);
    y = MIN(MAX(y, NSMinY(visible) + 16.0), NSMaxY(visible) - height - 16.0);
    return NSMakeRect(x, y, width, height);
}

- (NSSize)guardConfirmationAssetSize {
    NSString *path = self.panelShellPath.length ? self.panelShellPath : self.stopPosePath;
    if (path.length) {
        NSImage *image = [[NSImage alloc] initWithContentsOfFile:path.stringByExpandingTildeInPath];
        if (image && image.size.width > 0.0 && image.size.height > 0.0) {
            return image.size;
        }
    }
    return NSMakeSize(1185.0, 1327.0);
}

- (void)clearStopSignWindows {
    for (NSWindow *window in self.stopSignWindows) {
        [window orderOut:nil];
    }
    [self.stopSignWindows removeAllObjects];
    [self.heroStopWindow orderOut:nil];
    self.heroStopWindow = nil;
}

- (void)clearTransientGuardWindows {
    [self.stopSignRestoreTimer invalidate];
    self.stopSignRestoreTimer = nil;
    [self.stopSignAnimationTimer invalidate];
    self.stopSignAnimationTimer = nil;
    [self.heroAnimationTimer invalidate];
    self.heroAnimationTimer = nil;
    [self clearStopSignWindows];
    [self.confirmationWindow orderOut:nil];
    self.confirmationWindow = nil;
    self.confirmationDecisionFile = nil;
}

- (void)showFinalDeletionConfirmationOnScreen:(NSScreen *)screen {
    if (!screen || !self.confirmationDecisionFile.length) return;
    [self.confirmationWindow orderOut:nil];

    NSRect frame = [self guardConfirmationFrameOnScreen:screen];
    CGFloat width = frame.size.width;
    CGFloat height = frame.size.height;

    NSWindow *window = [[NSWindow alloc] initWithContentRect:frame
                                                   styleMask:NSWindowStyleMaskBorderless
                                                     backing:NSBackingStoreBuffered
                                                       defer:NO
                                                      screen:screen];
    window.backgroundColor = NSColor.clearColor;
    window.opaque = NO;
    window.hasShadow = NO;
    window.level = NSFloatingWindowLevel + 2;
    window.ignoresMouseEvents = NO;
    window.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                                NSWindowCollectionBehaviorFullScreenAuxiliary |
                                NSWindowCollectionBehaviorStationary;

    NSView *stage = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, width, height)];
    stage.wantsLayer = YES;
    stage.layer.backgroundColor = NSColor.clearColor.CGColor;
    stage.layer.masksToBounds = NO;

    if (self.panelShellPath.length) {
        GuardPoseView *shell = [[GuardPoseView alloc] initWithPosePath:self.panelShellPath];
        shell.frame = NSMakeRect(0, 0, width, height);
        shell.wantsLayer = YES;
        shell.layer.masksToBounds = NO;
        [stage addSubview:shell];
    } else {
        CGFloat panelWidth = width * 0.690;
        CGFloat panelHeight = height * 0.420;
        GuardPanelView *panel = [[GuardPanelView alloc] initWithFrame:NSMakeRect(width * 0.155,
                                                                                 height * 0.100,
                                                                                 panelWidth,
                                                                                 panelHeight)];
        [stage addSubview:panel];
    }

    CGFloat contentX = width * 0.155;
    CGFloat contentY = height * 0.100;
    CGFloat contentWidth = width * 0.690;
    CGFloat contentHeight = height * 0.420;

    NSString *guardName = self.petName.length ? self.petName : @"Hermes";
    NSString *protocolText = [[NSString stringWithFormat:@"%@ GUARD PROTOCOL", guardName] uppercaseString];
    NSTextField *protocol = [NSTextField labelWithString:protocolText];
    protocol.font = [NSFont boldSystemFontOfSize:12.0];
    protocol.textColor = [NSColor colorWithCalibratedRed:1.0 green:0.48 blue:0.08 alpha:0.95];
    protocol.alignment = NSTextAlignmentLeft;
    protocol.frame = NSMakeRect(contentX + 48, contentY + contentHeight - 34, contentWidth - 96, 18);
    [stage addSubview:protocol];

    NSTextField *title = [NSTextField labelWithString:@"Are you sure?"];
    title.font = [NSFont boldSystemFontOfSize:36.0];
    title.textColor = NSColor.whiteColor;
    title.alignment = NSTextAlignmentCenter;
    title.frame = NSMakeRect(contentX + 10, contentY + contentHeight - 126, contentWidth - 20, 46);
    [stage addSubview:title];

    NSString *subtitleText = [NSString stringWithFormat:@"%@ is blocking this deletion\nuntil you confirm.", guardName];
    NSTextField *subtitle = [NSTextField labelWithString:subtitleText];
    subtitle.font = [NSFont systemFontOfSize:20.0 weight:NSFontWeightMedium];
    subtitle.textColor = NSColor.whiteColor;
    subtitle.alphaValue = 0.82;
    subtitle.alignment = NSTextAlignmentCenter;
    subtitle.frame = NSMakeRect(contentX + 28, contentY + contentHeight - 196, contentWidth - 56, 52);
    [stage addSubview:subtitle];

    NSButton *cancel = [NSButton buttonWithTitle:@"Cancel" target:self action:@selector(cancelDeletionConfirmation:)];
    cancel.bezelStyle = NSBezelStyleRegularSquare;
    cancel.bordered = NO;
    cancel.wantsLayer = YES;
    cancel.layer.backgroundColor = [NSColor colorWithCalibratedRed:0.17 green:0.20 blue:0.24 alpha:1.0].CGColor;
    cancel.layer.cornerRadius = 9.0;
    cancel.attributedTitle = [[NSAttributedString alloc] initWithString:@"Cancel"
                                                             attributes:@{
        NSForegroundColorAttributeName: NSColor.whiteColor,
        NSFontAttributeName: [NSFont boldSystemFontOfSize:18.0]
    }];
    cancel.frame = NSMakeRect(contentX + 36, contentY + 28, 150, 56);
    [stage addSubview:cancel];

    NSButton *confirm = [NSButton buttonWithTitle:@"⌫  Delete" target:self action:@selector(approveDeletionConfirmation:)];
    confirm.bezelStyle = NSBezelStyleRegularSquare;
    confirm.bordered = NO;
    confirm.wantsLayer = YES;
    confirm.layer.backgroundColor = [NSColor colorWithCalibratedRed:0.78 green:0.16 blue:0.10 alpha:1.0].CGColor;
    confirm.layer.cornerRadius = 9.0;
    confirm.layer.borderWidth = 2.0;
    confirm.layer.borderColor = [NSColor colorWithCalibratedRed:1.0 green:0.54 blue:0.10 alpha:0.95].CGColor;
    confirm.attributedTitle = [[NSAttributedString alloc] initWithString:@"⌫  Delete"
                                                              attributes:@{
        NSForegroundColorAttributeName: NSColor.whiteColor,
        NSFontAttributeName: [NSFont boldSystemFontOfSize:18.0]
    }];
    confirm.keyEquivalent = @"\r";
    confirm.frame = NSMakeRect(contentX + contentWidth - 186, contentY + 28, 150, 56);
    [stage addSubview:confirm];

    window.contentView = stage;
    self.confirmationWindow = window;
    [window orderFrontRegardless];
}

- (void)showDeletionConfirmation:(NSString *)decisionFile {
    if (![self isAwake]) return;

    self.confirmationDecisionFile = decisionFile;
    [self.activityIdleTimer invalidate];
    [self.stopSignRestoreTimer invalidate];
    [self.stopSignAnimationTimer invalidate];
    [self clearStopSignWindows];
    [self setAllWindowsState:@"running"];
    [self.stopSignRestoreTimer invalidate];
    self.stopSignRestoreTimer = nil;
    [self.confirmationWindow orderOut:nil];

    NSScreen *screen = self.windows.firstObject.screen ?: NSScreen.mainScreen ?: NSScreen.screens.firstObject;
    [self showConfirmationHeroOnScreen:screen];
}

- (void)approveDeletionConfirmation:(id)sender {
    [self writeConfirmationDecision:@"approve"];
}

- (void)cancelDeletionConfirmation:(id)sender {
    [self writeConfirmationDecision:@"cancel"];
}

- (void)writeConfirmationDecision:(NSString *)decision {
    if (self.confirmationDecisionFile.length) {
        NSString *content = [decision stringByAppendingString:@"\n"];
        [content writeToFile:self.confirmationDecisionFile
                  atomically:YES
                    encoding:NSUTF8StringEncoding
                       error:nil];
    }
    [self.confirmationWindow orderOut:nil];
    self.confirmationWindow = nil;
    self.confirmationDecisionFile = nil;
    [self.heroAnimationTimer invalidate];
    self.heroAnimationTimer = nil;
    [self.stopSignAnimationTimer invalidate];
    self.stopSignAnimationTimer = nil;
    [self clearStopSignWindows];
    for (NSDictionary *entry in self.stopSignAnimationFrames) {
        NSWindow *window = entry[@"window"];
        NSRect original = [entry[@"original"] rectValue];
        [window setFrame:original display:YES animate:NO];
    }
    self.stopSignAnimationFrames = nil;
    for (NSWindow *window in self.windows) {
        [window orderFrontRegardless];
    }
    [self setAllWindowsState:@"idle"];
}

- (void)checkModeFile {
    if (!self.modeFilePath.length) return;

    NSError *error = nil;
    NSString *content = [NSString stringWithContentsOfFile:self.modeFilePath
                                                  encoding:NSUTF8StringEncoding
                                                     error:&error];
    if (!content.length || [content isEqualToString:self.lastModeFileContent]) return;

    self.lastModeFileContent = content;
    NSArray<NSString *> *parts = [content componentsSeparatedByCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSString *mode = parts.firstObject ?: @"";
    BOOL unlocked = [mode isEqualToString:@"unlock"];

    for (NSWindow *window in self.windows) {
        window.ignoresMouseEvents = !unlocked;
    }
}

- (BOOL)currentModeIsUnlocked {
    NSString *content = [NSString stringWithContentsOfFile:self.modeFilePath
                                                  encoding:NSUTF8StringEncoding
                                                     error:nil];
    NSArray<NSString *> *parts = [content componentsSeparatedByCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    return [parts.firstObject isEqualToString:@"unlock"];
}

- (BOOL)isAwake {
    return [NSFileManager.defaultManager fileExistsAtPath:self.awakeFilePath];
}

- (NSString *)positionKeyForScreen:(NSScreen *)screen {
    NSRect frame = screen.frame;
    return [NSString stringWithFormat:@"%.0f,%.0f,%.0f,%.0f",
            frame.origin.x, frame.origin.y, frame.size.width, frame.size.height];
}

- (NSDictionary<NSString *, NSValue *> *)savedPositions {
    NSString *content = [NSString stringWithContentsOfFile:self.positionFilePath
                                                  encoding:NSUTF8StringEncoding
                                                     error:nil];
    if (!content.length) return @{};

    NSMutableDictionary<NSString *, NSValue *> *positions = [NSMutableDictionary dictionary];
    for (NSString *line in [content componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
        NSArray<NSString *> *parts = [line componentsSeparatedByString:@" "];
        if (parts.count != 3) continue;
        positions[parts[0]] = [NSValue valueWithPoint:NSMakePoint(parts[1].doubleValue, parts[2].doubleValue)];
    }
    return positions;
}

- (void)saveWindowPositions {
    NSMutableArray<NSString *> *lines = [NSMutableArray array];
    for (OverlayWindow *window in self.windows) {
        if (!window.positionKey.length) continue;
        [lines addObject:[NSString stringWithFormat:@"%@ %.2f %.2f",
                          window.positionKey, window.frame.origin.x, window.frame.origin.y]];
    }

    NSString *content = [[lines componentsJoinedByString:@"\n"] stringByAppendingString:@"\n"];
    [content writeToFile:self.positionFilePath atomically:YES encoding:NSUTF8StringEncoding error:nil];
}

- (void)installActivityMonitors {
    if (HasArgument(@"--no-activity-monitor")) return;

    self.eventMonitors = [NSMutableArray array];
    NSEventMask mask = NSEventMaskKeyDown |
                       NSEventMaskLeftMouseDown |
                       NSEventMaskRightMouseDown |
                       NSEventMaskOtherMouseDown |
                       NSEventMaskScrollWheel;
    id monitor = [NSEvent addGlobalMonitorForEventsMatchingMask:mask
                                                        handler:^(NSEvent *event) {
        [self handleActivityEvent:event];
    }];
    if (monitor) [self.eventMonitors addObject:monitor];

    [self installKeyboardEventTap];
}

- (void)installKeyboardEventTap {
    NSDictionary *options = @{(__bridge id)kAXTrustedCheckOptionPrompt: @YES};
    AXIsProcessTrustedWithOptions((__bridge CFDictionaryRef)options);

    CGEventMask mask = CGEventMaskBit(kCGEventKeyDown);
    self.keyboardEventTap = CGEventTapCreate(kCGSessionEventTap,
                                             kCGHeadInsertEventTap,
                                             kCGEventTapOptionListenOnly,
                                             mask,
                                             KeyboardEventTapCallback,
                                             (__bridge void *)self);
    if (!self.keyboardEventTap) {
        fprintf(stderr, "Hermes Pet Overlay could not install keyboard event tap. Enable Accessibility permission for Hermes Pet Overlay.\n");
        return;
    }

    self.keyboardRunLoopSource = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, self.keyboardEventTap, 0);
    CFRunLoopAddSource(CFRunLoopGetMain(), self.keyboardRunLoopSource, kCFRunLoopCommonModes);
    CGEventTapEnable(self.keyboardEventTap, true);
}

- (void)handleActivityEvent:(NSEvent *)event {
    if (![self isAwake]) return;
    if ([self currentModeIsUnlocked]) return;

    if (event.type == NSEventTypeKeyDown) {
        [self handleKeyboardKeyCode:event.keyCode];
        return;
    }

    [self.pendingWorkTimer invalidate];
    self.pendingWorkTimer = nil;
    [self showActivityState:event.type == NSEventTypeScrollWheel ? @"review" : @"running"
                  idleDelay:0.75];
}

- (void)handleKeyboardKeyCode:(int64_t)keyCode {
    if (![self isAwake]) return;
    if ([self currentModeIsUnlocked]) return;

    if (keyCode == ReturnKeyCode || keyCode == KeypadEnterKeyCode) {
        [self showActivityState:@"review" idleDelay:3.0];
        [self startPendingWorkTimer];
    } else {
        [self.pendingWorkTimer invalidate];
        self.pendingWorkTimer = nil;
        [self showActivityState:@"running" idleDelay:0.65];
    }
}

- (void)startPendingWorkTimer {
    [self.pendingWorkTimer invalidate];
    self.pendingWorkTimer = [NSTimer scheduledTimerWithTimeInterval:12.0
                                                            repeats:NO
                                                              block:^(NSTimer *timer) {
        if (![self isAwake]) return;
        if ([self currentModeIsUnlocked]) return;
        [self playStopSignEffect];
    }];
}

- (void)showActivityState:(NSString *)state idleDelay:(NSTimeInterval)idleDelay {
    [self setAllWindowsState:state];

    [self.activityIdleTimer invalidate];
    self.activityIdleTimer = [NSTimer scheduledTimerWithTimeInterval:idleDelay
                                                              target:self
                                                            selector:@selector(returnToQuietIdle)
                                                            userInfo:nil
                                                             repeats:NO];
}

- (void)returnToQuietIdle {
    if (![self isAwake]) return;
    if ([self currentModeIsUnlocked]) return;
    [self setAllWindowsState:@"idle"];
}

@end

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        NSString *sendState = ArgumentValue(@"--send");
        if (sendState) {
            NSString *stateFilePath = ArgumentValue(@"--state-file") ?: DefaultStateFile;
            NSString *message = ArgumentValue(@"--message") ?: @"";
            if (!IsKnownState(sendState) &&
                ![sendState isEqualToString:@"stop-sign"] &&
                ![sendState hasPrefix:@"confirm-delete "]) {
                fprintf(stderr, "Unknown Hermes pet state: %s\n", sendState.UTF8String);
                return 2;
            }

            NSString *payload = [NSString stringWithFormat:@"%@ %.6f %@\n",
                                 sendState,
                                 NSDate.date.timeIntervalSince1970,
                                 message];
            NSError *error = nil;
            BOOL ok = [payload writeToFile:stateFilePath
                                atomically:YES
                                  encoding:NSUTF8StringEncoding
                                     error:&error];
            if (!ok) {
                fprintf(stderr, "Could not write Hermes pet state file %s: %s\n",
                        stateFilePath.UTF8String,
                        error.localizedDescription.UTF8String);
                return 1;
            }
            return 0;
        }

        NSString *sendMode = ArgumentValue(@"--mode");
        if (sendMode) {
            NSString *modeFilePath = ArgumentValue(@"--mode-file") ?: DefaultModeFile;
            if (![sendMode isEqualToString:@"lock"] && ![sendMode isEqualToString:@"unlock"]) {
                fprintf(stderr, "Unknown Hermes pet mode: %s\n", sendMode.UTF8String);
                return 2;
            }

            NSString *payload = [NSString stringWithFormat:@"%@ %.6f\n", sendMode, NSDate.date.timeIntervalSince1970];
            NSError *error = nil;
            BOOL ok = [payload writeToFile:modeFilePath
                                atomically:YES
                                  encoding:NSUTF8StringEncoding
                                     error:&error];
            if (!ok) {
                fprintf(stderr, "Could not write Hermes pet mode file %s: %s\n",
                        modeFilePath.UTF8String,
                        error.localizedDescription.UTF8String);
                return 1;
            }
            return 0;
        }

        NSApplication *application = NSApplication.sharedApplication;
        AppDelegate *delegate = [[AppDelegate alloc] init];
        application.delegate = delegate;
        [application run];
    }
    return 0;
}
