<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld" version="1.0.0">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>GAEZ-V5_YLD</sld:Name>
      <sld:Title>YLD</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap>
              <sld:ColorMapEntry color="#ffffff" opacity="0.0" quantity="-9.0" label="No Data"/>
              <sld:ColorMapEntry color="#ffffff" opacity="1.0" quantity="0.0" label="0"/>
              <sld:ColorMapEntry color="#ab8964" opacity="1.0" quantity="1000.0" label="1,000"/>
              <sld:ColorMapEntry color="#f18f3c" opacity="1.0" quantity="2500.0" label="2,500"/>
              <sld:ColorMapEntry color="#f7d909" opacity="1.0" quantity="5000.0" label="5,000"/>
              <sld:ColorMapEntry color="#67ca3b" opacity="1.0" quantity="7500.0" label="7,500"/>
              <sld:ColorMapEntry color="#0e8407" opacity="1.0" quantity="10000.0" label="10,000"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
