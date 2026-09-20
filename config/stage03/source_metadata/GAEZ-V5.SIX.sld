<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld" version="1.0.0">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>GAEZ-V5_SIX</sld:Name>
      <sld:Title>SIX</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="values">
              <sld:ColorMapEntry color="#ffffff" opacity="0.0" quantity="0.0" label="no data"/>
              <sld:ColorMapEntry color="#007000" opacity="1.0" quantity="1.0" label="SI &gt;85 : Very high"/>
              <sld:ColorMapEntry color="#15ae11" opacity="1.0" quantity="2.0" label="SI &gt;70 : High"/>
              <sld:ColorMapEntry color="#ace15e" opacity="1.0" quantity="3.0" label="SI &gt;55 : Good"/>
              <sld:ColorMapEntry color="#fed801" opacity="1.0" quantity="4.0" label="SI &gt;40 : Medium"/>
              <sld:ColorMapEntry color="#ce9d53" opacity="1.0" quantity="5.0" label="SI &gt;25 : Moderate"/>
              <sld:ColorMapEntry color="#cd6c01" opacity="1.0" quantity="6.0" label="SI &gt;10 : Marginal"/>
              <sld:ColorMapEntry color="#808080" opacity="1.0" quantity="7.0" label="SI &gt;0 : Very marginal"/>
              <sld:ColorMapEntry color="#cfcfcf" opacity="1.0" quantity="8.0" label="Not suitable"/>
              <sld:ColorMapEntry color="#aad3df" opacity="1.0" quantity="9.0" label="Water"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
