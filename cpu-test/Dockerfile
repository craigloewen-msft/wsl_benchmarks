FROM ubuntu:22.04

# phoronix test suite version
# see: https://github.com/phoronix-test-suite/phoronix-test-suite/releases
ARG version=10.8.4

ARG DEBIAN_FRONTEND=noninteractive
RUN apt update \
  && apt -y install wget unzip php-cli apt-utils mesa-utils php-xml git-core apt-file zlib1g-dev libaio1 libaio-dev \
  && apt-file update

WORKDIR /opt
RUN wget https://github.com/phoronix-test-suite/phoronix-test-suite/releases/download/v${version}/phoronix-test-suite-${version}.tar.gz -O pts.tar.gz \
  && tar xzf pts.tar.gz \
  && rm pts.tar.gz \
  && mv /opt/phoronix-test-suite /phoronix-test-suite

WORKDIR /phoronix-test-suite
# CMD [ "./phoronix-test-suite", "shell" ]

#CMD ["./phoronix-test-suite", "PTS_SILENT_MODE=1 TEST_RESULTS_NAME=smallpt TEST_RESULTS_IDENTIFIER=ci TEST_RUNS=3 ./phoronix-test-suite batch-benchmark pts/smallpt | grep -A 1 'Average:'"]

# CMD ["/bin/bash", "-c", "PTS_SILENT_MODE=1 TEST_RESULTS_NAME=smallpt TEST_RESULTS_IDENTIFIER=ci TEST_RUNS=3 ./phoronix-test-suite batch-benchmark pts/smallpt | grep -A 1 'Average:'"]
CMD ["/bin/bash", "-c", "PTS_SILENT_MODE=1 TEST_RESULTS_NAME=smallptresults TEST_RESULTS_IDENTIFIER=ci TEST_RESULTS_DESCRIPTION=smallptdescription TEST_RUNS=3 ./phoronix-test-suite benchmark pts/smallpt"]
