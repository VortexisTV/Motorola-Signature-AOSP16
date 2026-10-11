package vantage.telephony.imsnetwork;

import android.app.Application;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.TelephonyNetworkSpecifier;
import android.telephony.SubscriptionInfo;
import android.telephony.SubscriptionManager;
import android.util.ArrayMap;
import android.util.ArraySet;
import android.util.Log;

import java.util.List;

/**
 * Keeps one IMS network request alive per active subscription.
 *
 * The request is identical to the one the stock CNE app holds
 * (Transports: CELLULAR, Capabilities: IMS, Specifier: TelephonyNetworkSpecifier[subId]).
 * Telephony creates its IMS data network, and can hand it over between WWAN and WLAN, only
 * while such a request exists.
 */
public class ImsNetworkApp extends Application {
    private static final String TAG = "VantageImsNetwork";

    private final ArrayMap<Integer, ConnectivityManager.NetworkCallback> mRequests = new ArrayMap<>();
    private ConnectivityManager mConnectivityManager;
    private SubscriptionManager mSubscriptionManager;

    @Override
    public void onCreate() {
        super.onCreate();
        mConnectivityManager = getSystemService(ConnectivityManager.class);
        mSubscriptionManager = getSystemService(SubscriptionManager.class);
        if (mConnectivityManager == null || mSubscriptionManager == null) {
            Log.e(TAG, "connectivity or subscription service missing; no IMS network request");
            return;
        }
        try {
            mSubscriptionManager.addOnSubscriptionsChangedListener(getMainExecutor(),
                    new SubscriptionManager.OnSubscriptionsChangedListener() {
                        @Override
                        public void onSubscriptionsChanged() {
                            syncRequests();
                        }
                    });
        } catch (RuntimeException e) {
            Log.e(TAG, "cannot listen for subscription changes", e);
        }
        syncRequests();
    }

    /** Runs on the main thread only. */
    private void syncRequests() {
        final ArraySet<Integer> active = new ArraySet<>();
        try {
            final List<SubscriptionInfo> subscriptions =
                    mSubscriptionManager.getActiveSubscriptionInfoList();
            if (subscriptions != null) {
                for (SubscriptionInfo info : subscriptions) {
                    active.add(info.getSubscriptionId());
                }
            }
        } catch (RuntimeException e) {
            Log.e(TAG, "cannot read the active subscriptions", e);
            return;
        }

        for (int i = mRequests.size() - 1; i >= 0; i--) {
            final int subId = mRequests.keyAt(i);
            if (!active.contains(subId)) {
                try {
                    mConnectivityManager.unregisterNetworkCallback(mRequests.valueAt(i));
                } catch (RuntimeException e) {
                    Log.w(TAG, "releasing the request of subscription " + subId + " failed", e);
                }
                mRequests.removeAt(i);
                Log.i(TAG, "released IMS network request of subscription " + subId);
            }
        }
        for (int subId : active) {
            if (!mRequests.containsKey(subId)) {
                request(subId);
            }
        }
    }

    private void request(final int subId) {
        final NetworkRequest request = new NetworkRequest.Builder()
                .addTransportType(NetworkCapabilities.TRANSPORT_CELLULAR)
                .addCapability(NetworkCapabilities.NET_CAPABILITY_IMS)
                .setNetworkSpecifier(new TelephonyNetworkSpecifier.Builder()
                        .setSubscriptionId(subId).build())
                .build();
        final ConnectivityManager.NetworkCallback callback =
                new ConnectivityManager.NetworkCallback() {
                    @Override
                    public void onAvailable(Network network) {
                        Log.i(TAG, "IMS network " + network + " available, subscription " + subId);
                    }

                    @Override
                    public void onLost(Network network) {
                        Log.i(TAG, "IMS network " + network + " lost, subscription " + subId);
                    }
                };
        try {
            mConnectivityManager.requestNetwork(request, callback);
            mRequests.put(subId, callback);
            Log.i(TAG, "requested IMS network for subscription " + subId);
        } catch (RuntimeException e) {
            Log.e(TAG, "IMS network request for subscription " + subId + " was refused", e);
        }
    }
}
