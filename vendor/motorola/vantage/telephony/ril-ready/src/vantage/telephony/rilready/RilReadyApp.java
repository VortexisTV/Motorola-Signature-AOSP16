package vantage.telephony.rilready;

import android.app.Application;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.os.Binder;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Parcel;
import android.os.RemoteException;
import android.os.ServiceManager;
import android.telephony.SubscriptionInfo;
import android.telephony.SubscriptionManager;
import android.telephony.TelephonyCallback;
import android.telephony.TelephonyManager;
import android.telephony.ims.ImsException;
import android.telephony.ims.ImsMmTelManager;
import android.telephony.ims.ImsStateCallback;
import android.util.Log;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executor;

/**
 * Sends the Qualcomm RIL the "Android telephony is ready" message, once per SIM slot, and again
 * after a RIL or modem restart. Until it arrives the RIL keeps incoming SMS to itself.
 * The conditions are those of the stock sender (README.md).
 */
public class RilReadyApp extends Application {
    private static final String TAG = "VantageRilReady";

    // vendor.qti.hardware.radio.qcrilhook, AIDL version 1 (frozen). Method numbers and argument
    // order as in the stock client (qcrilmsgtunnel.apk).
    private static final String HOOK = "vendor.qti.hardware.radio.qcrilhook.IQtiOemHook";
    private static final int HOOK_SET_CALLBACK = IBinder.FIRST_CALL_TRANSACTION;
    private static final int HOOK_RAW_REQUEST = IBinder.FIRST_CALL_TRANSACTION + 1;
    private static final int CALLBACK_METHOD = IBinder.FIRST_CALL_TRANSACTION;

    // QCRIL_EVT_HOOK_SET_ATEL_UI_STATUS: OEM hook base 0x80000 + 26; payload one byte, 1 = ready.
    private static final int SET_ATEL_UI_STATUS = 0x80000 + 26;
    // Stock asks for the IMS state up to 120 times, one second apart, then goes ahead.
    private static final long IMS_WAIT_MS = 120_000;

    private Handler mHandler;
    private Executor mExecutor;
    private TelephonyManager mTelephony;
    private SubscriptionManager mSubscriptions;
    private boolean mImsSupported;
    private Slot[] mSlots;
    private int mSerial;

    private final class Slot implements IBinder.DeathRecipient {
        final int index;
        IBinder hal;
        boolean lookingUp;
        boolean sent;
        int imsSubId = SubscriptionManager.INVALID_SUBSCRIPTION_ID;
        ImsMmTelManager imsManager;
        ImsStateCallback imsCallback;
        boolean imsUp;
        boolean imsTimedOut;
        final Runnable imsTimeout;

        Slot(int index) {
            this.index = index;
            imsTimeout = () -> {
                imsTimedOut = true;
                Log.w(TAG, "slot " + index + ": the IMS stack is still not up, not waiting any longer");
                evaluate(this);
            };
        }

        @Override
        public void binderDied() {
            mHandler.post(() -> {
                Log.w(TAG, "slot " + index + ": the RIL died, the signal will be sent again");
                hal = null;
                sent = false;
                evaluate(this);
            });
        }
    }

    /** IQtiOemHookResponse / IQtiOemHookIndication: only the answer to our request is of interest. */
    private final class Callback extends Binder {
        private final String mDescriptor;
        private final int mSlot;
        private final boolean mIsResponse;

        Callback(String descriptor, int slot, boolean isResponse) {
            mDescriptor = descriptor;
            mSlot = slot;
            mIsResponse = isResponse;
            markVintfStability();   // the caller is a vendor process
            attachInterface(null, descriptor);
        }

        @Override
        protected boolean onTransact(int code, Parcel data, Parcel reply, int flags) throws RemoteException {
            if (code != CALLBACK_METHOD) {
                return super.onTransact(code, data, reply, flags);
            }
            data.enforceInterface(mDescriptor);
            if (mIsResponse) {   // oemHookRawResponse(int serial, RadioError error, byte[] data)
                int serial = data.readInt();
                int error = data.readInt();
                Log.i(TAG, "slot " + mSlot + ": the RIL answered request " + serial + " with error " + error
                        + (error == 0 ? " (accepted)" : ""));
            }
            return true;
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        HandlerThread thread = new HandlerThread(TAG);
        thread.start();
        mHandler = new Handler(thread.getLooper());
        mExecutor = mHandler::post;
        mTelephony = getSystemService(TelephonyManager.class);
        mSubscriptions = getSystemService(SubscriptionManager.class);
        mImsSupported = getPackageManager().hasSystemFeature(PackageManager.FEATURE_TELEPHONY_IMS);
        mSlots = new Slot[Math.max(1, mTelephony.getActiveModemCount())];
        for (int i = 0; i < mSlots.length; i++) {
            mSlots[i] = new Slot(i);
        }

        IntentFilter filter = new IntentFilter();
        filter.addAction(TelephonyManager.ACTION_SIM_CARD_STATE_CHANGED);
        filter.addAction(TelephonyManager.ACTION_SIM_APPLICATION_STATE_CHANGED);
        registerReceiver(new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                evaluateAll();
            }
        }, filter, null, mHandler, Context.RECEIVER_NOT_EXPORTED);
        mSubscriptions.addOnSubscriptionsChangedListener(mExecutor,
                new SubscriptionManager.OnSubscriptionsChangedListener() {
                    @Override
                    public void onSubscriptionsChanged() {
                        evaluateAll();
                    }
                });
        mTelephony.registerTelephonyCallback(mExecutor, new RadioListener());
        mHandler.post(this::evaluateAll);
        Log.i(TAG, "started: " + mSlots.length + " slots, IMS " + (mImsSupported ? "supported" : "not supported"));
    }

    /** A modem restart forgets the signal: forget that it was sent, send again when the radio is back. */
    private final class RadioListener extends TelephonyCallback implements TelephonyCallback.RadioPowerStateListener {
        @Override
        public void onRadioPowerStateChanged(int state) {
            if (state == TelephonyManager.RADIO_POWER_UNAVAILABLE) {
                for (Slot s : mSlots) {
                    s.sent = false;
                }
            } else {
                evaluateAll();
            }
        }
    }

    private void evaluateAll() {
        for (Slot s : mSlots) {
            evaluate(s);
        }
    }

    private void evaluate(Slot s) {
        if (s.sent) {
            return;
        }
        if (s.hal == null) {
            lookUp(s);
            return;
        }
        int sim = mTelephony.getSimState(s.index);
        if (sim != TelephonyManager.SIM_STATE_ABSENT) {
            // A SIM that is loaded or locked: wait for its subscription, the radio and the IMS stack.
            SubscriptionInfo info = mSubscriptions.getActiveSubscriptionInfoForSimSlotIndex(s.index);
            if (info == null) {
                Log.d(TAG, "slot " + s.index + ": SIM state " + sim + ", no subscription yet");
                return;
            }
            int subId = info.getSubscriptionId();
            if (mTelephony.createForSubscriptionId(subId).getRadioPowerState()
                    == TelephonyManager.RADIO_POWER_UNAVAILABLE) {
                Log.d(TAG, "slot " + s.index + ": radio unavailable");
                return;
            }
            if (mImsSupported && !s.imsTimedOut) {
                watchIms(s, subId);
                if (!s.imsUp) {
                    Log.d(TAG, "slot " + s.index + ": waiting for the IMS stack of subscription " + subId);
                    return;
                }
            }
        }
        send(s, sim);
    }

    /** The RIL registers one OEM hook service per slot; waiting for it must not block the handler. */
    private void lookUp(Slot s) {
        if (s.lookingUp) {
            return;
        }
        s.lookingUp = true;
        String name = HOOK + "/oemhook" + s.index;
        new Thread(() -> {
            IBinder binder = ServiceManager.waitForDeclaredService(name);
            mHandler.post(() -> {
                s.lookingUp = false;
                if (binder == null) {
                    Log.e(TAG, "slot " + s.index + ": " + name + " is not declared by this vendor");
                    return;
                }
                try {
                    binder.linkToDeath(s, 0);
                } catch (RemoteException e) {
                    lookUp(s);   // died in between: wait for the next instance
                    return;
                }
                s.hal = binder;
                registerCallbacks(s);
                evaluate(s);
            });
        }, TAG + "-lookup" + s.index).start();
    }

    /** setCallback(IQtiOemHookResponse, IQtiOemHookIndication): only to see the RIL's answer in the log. */
    private void registerCallbacks(Slot s) {
        Parcel data = Parcel.obtain(s.hal);
        try {
            data.writeInterfaceToken(HOOK);
            data.writeStrongBinder(new Callback(HOOK + "Response", s.index, true));
            data.writeStrongBinder(new Callback(HOOK + "Indication", s.index, false));
            s.hal.transact(HOOK_SET_CALLBACK, data, null, IBinder.FLAG_ONEWAY);
        } catch (RemoteException | RuntimeException e) {
            Log.w(TAG, "slot " + s.index + ": no answer callback (" + e + "); the signal is sent all the same");
        } finally {
            data.recycle();
        }
    }

    private void watchIms(Slot s, int subId) {
        if (s.imsSubId == subId && s.imsCallback != null) {
            return;
        }
        if (s.imsCallback != null) {
            s.imsManager.unregisterImsStateCallback(s.imsCallback);
        }
        if (s.imsSubId != subId) {
            s.imsUp = false;
            mHandler.removeCallbacks(s.imsTimeout);
            mHandler.postDelayed(s.imsTimeout, IMS_WAIT_MS);
        }
        s.imsSubId = subId;
        s.imsManager = ImsMmTelManager.createForSubscriptionId(subId);
        s.imsCallback = new ImsStateCallback() {
            @Override
            public void onAvailable() {
                s.imsUp = true;
                mHandler.removeCallbacks(s.imsTimeout);
                evaluate(s);
            }

            @Override
            public void onUnavailable(int reason) {
                s.imsUp = false;
            }

            @Override
            public void onError() {   // the callback is dead; a later evaluation registers a new one
                s.imsCallback = null;
            }
        };
        try {
            s.imsManager.registerImsStateCallback(mExecutor, s.imsCallback);
        } catch (ImsException e) {
            s.imsCallback = null;
            if (e.getCode() == ImsException.CODE_ERROR_UNSUPPORTED_OPERATION) {
                s.imsUp = true;   // no IMS for this subscription: nothing to wait for
            } else {
                mHandler.postDelayed(() -> evaluate(s), 1000);
            }
        }
    }

    private void send(Slot s, int simState) {
        byte[] head = "QOEMHOOK".getBytes(StandardCharsets.US_ASCII);
        ByteBuffer request = ByteBuffer.allocate(head.length + 8 + 1).order(ByteOrder.nativeOrder());
        request.put(head).putInt(SET_ATEL_UI_STATUS).putInt(1).put((byte) 1);
        int serial = ++mSerial;
        Parcel data = Parcel.obtain(s.hal);
        try {
            data.writeInterfaceToken(HOOK);
            data.writeInt(serial);
            data.writeByteArray(request.array());
            s.hal.transact(HOOK_RAW_REQUEST, data, null, IBinder.FLAG_ONEWAY);
            s.sent = true;
            Log.i(TAG, "slot " + s.index + ": told the RIL that telephony is ready (request " + serial
                    + ", SIM state " + simState + ")");
        } catch (RemoteException e) {
            Log.w(TAG, "slot " + s.index + ": the RIL went away while sending: " + e);
        } finally {
            data.recycle();
        }
    }
}
