#!/usr/bin/env bash
# Build sem Gradle: aapt + javac + dx + zipalign + apksigner.
# Requer: android.jar (API 34) em $ANDROID_JAR, e um keystore em $KEYSTORE.
set -euo pipefail
cd "$(dirname "$0")"
ANDROID_JAR=${ANDROID_JAR:?defina ANDROID_JAR}
KEYSTORE=${KEYSTORE:?defina KEYSTORE}
KS_PASS=${KS_PASS:?defina KS_PASS}
VERSION_CODE=25
VERSION_NAME=2.5
OUT=build
rm -rf $OUT && mkdir -p $OUT/gen $OUT/classes $OUT/dex

aapt package -f -m -J $OUT/gen -M AndroidManifest.xml -S res -A assets -I "$ANDROID_JAR" \
  --min-sdk-version 26 --target-sdk-version 34 \
  --version-code $VERSION_CODE --version-name $VERSION_NAME \
  -0 arsc -F $OUT/unsigned.apk

javac -nowarn -source 8 -target 8 -bootclasspath "$ANDROID_JAR" -encoding UTF-8 -Xlint:-options \
  -d $OUT/classes $(find src $OUT/gen -name '*.java')

dalvik-exchange --dex --min-sdk-version=26 --output=$OUT/dex/classes.dex $OUT/classes
(cd $OUT/dex && aapt add ../unsigned.apk classes.dex >/dev/null)

zipalign -f -p 4 $OUT/unsigned.apk $OUT/aligned.apk
apksigner sign --ks "$KEYSTORE" --ks-pass "pass:$KS_PASS" \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
  --out $OUT/Alerta-BTC-$VERSION_NAME.apk $OUT/aligned.apk
apksigner verify -v $OUT/Alerta-BTC-$VERSION_NAME.apk
echo "OK -> $OUT/Alerta-BTC-$VERSION_NAME.apk"
