SET ADS_DEPLOY_CONDA_ENV=ads-deploy-2.12.0
SET WINDOWS_ADS_IOC_TOP=c:/Repos/ads-ioc/R1.0.1

IF "%UseDocker%" == "0" (
    echo * Using ads-deploy conda environment: %ADS_DEPLOY_CONDA_ENV%
)
